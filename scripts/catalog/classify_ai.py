"""AI-assisted catalogue classification (SU11A-52). Offline and local: reads the
rule predictions and the export, calls the Claude Messages API, writes local
files. Never touches a database.

    python -m scripts.catalog.classify_ai --predictions RUN/predictions.csv.gz \\
        --export EXPORT.csv.gz --work-dir WORK --max-requests 900 \\
        [--model claude-haiku-5-5] [--concurrency 4] [--pilot 200] [--dry-run]
    python -m scripts.catalog.classify_ai --work-dir WORK --write-labels docs/catalog/ai_labels_v1.csv

Input set: items whose v1 rule result (rules + GS1) is unclassified, low or
medium, that have a name and are not pseudo items (db.search_norm.pseudo_pattern).
Per item the request carries only a batch index, the normalised name, the
manufacturer when it is not a placeholder, and the GS1 group when there is one
(--hide-gs1 leaves the group out, for the pilot's GS1 benchmark).

Requests: batches of --batch-size (50) items; system prompt = instructions + the
v1 category list (id + Hebrew path), cached (cache_control, 5-minute TTL; every
batch reuses it); thinking off; structured output (JSON schema with an enum of
the v1 ids + "unknown"), and every returned id is validated again here.

Safety rails:
  - the API key is read from the environment variable XXL_CAT_AI_KEY only and
    passed to the client explicitly; it is never printed, logged or written;
  - --max-requests is a hard budget (required for a live run): no request is
    sent beyond it;
  - the run stops after --max-errors consecutive failed batches (after the
    SDK's own retries with backoff: 429 / 5xx / connection);
  - concurrency is capped at 4;
  - resumable: each finished batch is appended to WORK/checkpoint.jsonl and its
    items are skipped on the next run; items a response left out are retried.
Run log: WORK/run_log.jsonl (one line per request: batch size, token usage,
latency, error class) and WORK/summary.json (totals and estimated cost).
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.catalog.classify_rules as C  # noqa: E402
from db.search_norm import normalize, pseudo_pattern  # noqa: E402

KEY_ENV = "XXL_CAT_AI_KEY"
DEFAULT_MODEL = "claude-haiku-5-5"
MAX_CONCURRENCY = 4
UNKNOWN = "unknown"
CONFIDENCES = ("high", "medium", "low")
# USD per million tokens: (input, output). Cache writes 1.25x input (5-minute
# TTL), cache reads 0.1x input. Haiku 5.5 prices are for prompts <= 100K tokens.
PRICES = {
    "claude-haiku-5-5": (0.10, 0.50),
    "claude-sonnet-5-5": (2.00, 10.00),
    "claude-opus-5-5": (4.00, 20.00),
}
CACHE_WRITE_X, CACHE_READ_X = 1.25, 0.10

INSTRUCTIONS = """You classify Israeli supermarket products into a fixed category tree.

Each user message is a JSON list of products. Every product has:
  i    its index in this batch (copy it back unchanged)
  n    the product name as the chain publishes it: Hebrew, often truncated to about 20 characters, sometimes with the brand first, sizes and pack words mixed in
  m    the manufacturer, when known
  g    the GS1 product group (English), when known - a strong hint, but GS1 sometimes files products in the wrong group

For every product return exactly one object with:
  i            the same index
  category_id  the single best id from the list below. Prefer the deepest id you are sure of (a sub-type over its category, a category over its department); use a department id when only the aisle is clear. Use "unknown" when the name gives too little to decide (for example a bare brand or a code).
  confidence   high = clear from the name; medium = most likely; low = a guess
  reason       at most six words, in English

Rules of the tree (decisions of the shop owner):
- One primary category per product. Traits such as kosher, organic, gluten-free, vegan, sugar-free, size or flavour are NOT categories.
- Frozen products go to the freezer department D06 (frozen fruit is D06.C02, frozen vegetables D06.C01, frozen bakery and pizza D06.C04, schnitzel and nuggets D06.C05), except raw frozen meat, poultry and fish, which stay in D03.
- Crackers and cookies are snacks (D08). Ice-cream bars are ice cream (D06.C03).
- Baby toiletries, baby food and baby gear are baby (D13). Toilet blocks are cleaning (D11.C04).
- Pickles and olives are deli (D04.C05). Ready hummus, masabacha and prepared tahini salads are deli (D04.C02); raw tahini paste and nut butters are pantry spreads (D07.C20). Dry chickpeas are pantry pulses (D07.C05).
- Cooking sauces (D07.C10) and table condiments such as ketchup, mayonnaise and mustard (D07.C11) are separate; salad dressings and vinegar are D07.C12.
- Sliced and smoked deli meat, sausages and hot dogs are D04.C01; raw meat is D03.
- Tobacco and smoking products are D10.C05; liqueurs are D10.C04.
- Non-food: household goods and kitchenware are D15; clothing, toys, party goods, candles, Judaica and stationery are D16; personal care and pharmacy are D12.
- "צ'יפס" alone is French fries (frozen, D06.C06); crisps are D08.C05.S01.

Categories (id | Hebrew path):
"""


def _md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()


# --------------------------------------------------------------------------- inputs
def taxonomy_lines(tax: C.Taxonomy) -> list[str]:
    return [f"{nid} | {tax.path_he(nid)}" for nid in tax.nodes]


def system_prompt(tax: C.Taxonomy) -> str:
    return INSTRUCTIONS + "\n".join(taxonomy_lines(tax)) + "\n"


def output_schema(tax: C.Taxonomy) -> dict:
    return {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "i": {"type": "integer"},
                        "category_id": {"type": "string", "enum": [*tax.nodes, UNKNOWN]},
                        "confidence": {"type": "string", "enum": list(CONFIDENCES)},
                        "reason": {"type": "string"},
                    },
                    "required": ["i", "category_id", "confidence", "reason"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["items"],
        "additionalProperties": False,
    }


def item_payload(r: dict, hide_gs1: bool = False) -> dict:
    """What the API sees about one item: name, real manufacturer, GS1 group."""
    out = {"n": normalize(C.item_name(r))}
    mfr = (r.get("manufacturer") or "").strip()
    if mfr and not C.PLACEHOLDER_MFR.match(normalize(mfr).strip(" .,-'\"")):
        out["m"] = mfr
    if r.get("gs1_group") and not hide_gs1:
        out["g"] = r["gs1_group"]
    return out


def select_items(pred: list[dict], export: dict[str, dict]) -> list[dict]:
    """Export rows to send: v1 confidence unclassified / low / medium, named, not pseudo."""
    out = []
    for p in pred:
        if (p.get("confidence") or "") not in ("", "low", "medium"):
            continue
        r = export.get(p["item_code"])
        if r is None:
            continue
        name = normalize(C.item_name(r))
        if not name or pseudo_pattern(name):
            continue
        out.append(r)
    return out


def batches(rows: list[dict], size: int) -> list[list[dict]]:
    return [rows[i:i + size] for i in range(0, len(rows), size)]


# --------------------------------------------------------------------------- output
def parse_response(text: str, batch: list[dict], valid_ids: set[str], model: str) -> tuple[list[dict], list[str]]:
    """Validated labels for a batch, and the item_codes the response left out.

    An item whose index is unknown, repeated or out of range, whose id is not
    in the taxonomy (and not "unknown") or whose confidence is invalid is
    dropped (and counted as missing, so a resumed run retries it).
    """
    data = json.loads(text)
    seen: dict[int, dict] = {}
    for x in data.get("items") or []:
        try:
            i = int(x["i"])
        except (KeyError, TypeError, ValueError):
            continue
        if not 0 <= i < len(batch) or i in seen:
            continue
        cid, conf = str(x.get("category_id") or ""), str(x.get("confidence") or "")
        if (cid not in valid_ids and cid != UNKNOWN) or conf not in CONFIDENCES:
            continue
        seen[i] = {"item_code": batch[i]["item_code"], "category_id": cid, "confidence": conf,
                   "reason": " ".join(str(x.get("reason") or "").split())[:120], "model": model}
    missing = [batch[i]["item_code"] for i in range(len(batch)) if i not in seen]
    return [seen[i] for i in sorted(seen)], missing


def usage_dict(u) -> dict:
    g = (lambda k: int(getattr(u, k, 0) or 0)) if not isinstance(u, dict) else (lambda k: int(u.get(k) or 0))
    return {k: g(k) for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens", "cache_read_input_tokens")}


def cost_usd(model: str, usage: dict) -> float:
    pin, pout = PRICES.get(model, PRICES[DEFAULT_MODEL])
    return (usage.get("input_tokens", 0) * pin + usage.get("output_tokens", 0) * pout
            + usage.get("cache_creation_input_tokens", 0) * pin * CACHE_WRITE_X
            + usage.get("cache_read_input_tokens", 0) * pin * CACHE_READ_X) / 1e6


# --------------------------------------------------------------------------- api
def make_client(max_retries: int = 4):
    """Anthropic client with the key from XXL_CAT_AI_KEY (never from ANTHROPIC_API_KEY)."""
    key = os.environ.get(KEY_ENV)
    if not key:
        raise SystemExit(f"{KEY_ENV} is not set - no API call made")
    import anthropic
    return anthropic.Anthropic(api_key=key, max_retries=max_retries, timeout=180.0)


def call_batch(client, model: str, system: str, schema: dict, payload: list[dict], max_tokens: int,
               effort: str = ""):
    """One Messages request; returns (text, usage dict, stop_reason).

    effort "" = thinking off (the default); low / medium / high = adaptive
    thinking at that effort.
    """
    thinking = {"type": "adaptive"} if effort else {"type": "disabled"}
    output_config = {"format": {"type": "json_schema", "schema": schema}}
    if effort:
        output_config["effort"] = effort
    resp = client.messages.create(
        model=model,
        max_tokens=max_tokens,
        thinking=thinking,
        system=[{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}],
        messages=[{"role": "user", "content": json.dumps(payload, ensure_ascii=False)}],
        output_config=output_config,
    )
    text = next((b.text for b in resp.content if getattr(b, "type", "") == "text"), "")
    return text, usage_dict(resp.usage), resp.stop_reason


class Budget:
    """Thread-safe request budget and consecutive-error breaker."""

    def __init__(self, max_requests: int, max_errors: int):
        self.left, self.max_errors, self.errors = max_requests, max_errors, 0
        self.stopped = ""
        self.lock = threading.Lock()

    def take(self) -> bool:
        with self.lock:
            if self.stopped or self.left <= 0:
                if not self.stopped and self.left <= 0:
                    self.stopped = "max-requests reached"
                return False
            self.left -= 1
            return True

    def result(self, ok: bool) -> None:
        with self.lock:
            self.errors = 0 if ok else self.errors + 1
            if self.errors >= self.max_errors and not self.stopped:
                self.stopped = f"{self.errors} consecutive errors"


def load_checkpoint(path: Path) -> dict[str, dict]:
    done: dict[str, dict] = {}
    if path.is_file():
        with open(path, encoding="utf-8") as fh:
            for line in fh:
                if line.strip():
                    for lab in json.loads(line).get("labels", []):
                        done[lab["item_code"]] = lab
    return done


def run(rows: list[dict], work: Path, client, model: str, tax: C.Taxonomy, batch_size: int,
        concurrency: int, max_requests: int, max_errors: int, hide_gs1: bool = False,
        max_tokens: int = 8000, call=call_batch, effort: str = "") -> dict:
    """Classify rows not yet in the checkpoint; returns the run summary."""
    work.mkdir(parents=True, exist_ok=True)
    ckpt, log_path = work / "checkpoint.jsonl", work / "run_log.jsonl"
    done = load_checkpoint(ckpt)
    todo = [r for r in rows if r["item_code"] not in done]
    system, schema, valid = system_prompt(tax), output_schema(tax), set(tax.nodes)
    budget = Budget(max_requests, max_errors)
    lock = threading.Lock()
    totals = {"requests": 0, "ok": 0, "failed": 0, "labels": 0, "missing": 0, "truncated": 0,
              "usage": {k: 0 for k in ("input_tokens", "output_tokens", "cache_creation_input_tokens",
                                       "cache_read_input_tokens")}}

    def one(batch: list[dict]) -> None:
        if not budget.take():
            return
        t0 = time.perf_counter()
        rec = {"at": datetime.now(timezone.utc).isoformat(timespec="seconds"), "items": len(batch), "model": model}
        try:
            text, usage, stop = call(client, model, system, schema,
                                     [{"i": i, **item_payload(r, hide_gs1)} for i, r in enumerate(batch)],
                                     max_tokens, effort)
            labels, missing = parse_response(text, batch, valid, model) if stop != "max_tokens" else ([], [r["item_code"] for r in batch])
            rec.update({"usage": usage, "stop_reason": stop, "labels": len(labels), "missing": len(missing)})
            ok = bool(labels)
        except Exception as exc:  # noqa: BLE001 - counted, logged by class only (no payloads, no key)
            usage, labels, missing, ok, stop = {}, [], [r["item_code"] for r in batch], False, ""
            rec.update({"error": type(exc).__name__, "status": getattr(exc, "status_code", None)})
        rec["ms"] = round((time.perf_counter() - t0) * 1000)
        budget.result(ok)
        with lock:
            totals["requests"] += 1
            totals["ok" if ok else "failed"] += 1
            totals["labels"] += len(labels)
            totals["missing"] += len(missing) if ok else 0
            totals["truncated"] += stop == "max_tokens"
            for k, v in usage.items():
                totals["usage"][k] += v
            if labels:
                with open(ckpt, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps({"labels": labels}, ensure_ascii=False) + "\n")
            with open(log_path, "a", encoding="utf-8") as fh:
                fh.write(json.dumps(rec) + "\n")
            n = totals["requests"]
            if n % 20 == 0:
                print(f"requests {n}: labels {totals['labels']}, failed {totals['failed']}, "
                      f"est ${cost_usd(model, totals['usage']):.3f}", file=sys.stderr, flush=True)

    t0 = time.perf_counter()
    todo_batches = batches(todo, batch_size)
    if todo_batches:
        one(todo_batches.pop(0))   # alone first: it writes the prompt cache the others read
    with ThreadPoolExecutor(max_workers=max(1, min(concurrency, MAX_CONCURRENCY))) as ex:
        futs = [ex.submit(one, b) for b in todo_batches]
        for f in as_completed(futs):
            f.result()
    summary = {"model": model, "effort": effort or "thinking off", "items_selected": len(rows), "already_done": len(rows) - len(todo),
               "todo": len(todo), **totals, "stopped": budget.stopped or "",
               "estimated_cost_usd": round(cost_usd(model, totals["usage"]), 4),
               "elapsed_s": round(time.perf_counter() - t0, 1),
               "labels_in_checkpoint": len(load_checkpoint(ckpt))}
    prev = json.loads((work / "summary.json").read_text(encoding="utf-8")) if (work / "summary.json").is_file() else {}
    runs = prev.get("runs", []) + [summary]
    agg = {k: sum(r["usage"][k] for r in runs) for k in summary["usage"]}
    (work / "summary.json").write_text(json.dumps(
        {"runs": runs, "total_requests": sum(r["requests"] for r in runs), "total_usage": agg,
         "total_estimated_cost_usd": round(cost_usd(model, agg), 4)}, indent=1), encoding="utf-8")
    return summary


def write_labels(work: Path, out: Path) -> int:
    labels = sorted(load_checkpoint(work / "checkpoint.jsonl").values(), key=lambda x: x["item_code"])
    with open(out, "w", encoding="utf-8", newline="") as fh:
        w = csv.DictWriter(fh, ["item_code", "category_id", "confidence", "reason", "model"], lineterminator="\n")
        w.writeheader()
        w.writerows(labels)
    return len(labels)


def load_ai_labels(path: Path) -> dict[str, dict]:
    with open(path, encoding="utf-8", newline="") as fh:
        return {r["item_code"]: r for r in csv.DictReader(fh)}


# --------------------------------------------------------------------------- main
def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--predictions", type=Path, help="classify_rules predictions.csv.gz (v1 rules + GS1)")
    ap.add_argument("--export", type=Path, help="the SU11A-52 export (names, manufacturer, GS1 group)")
    ap.add_argument("--work-dir", required=True, type=Path)
    ap.add_argument("--taxonomy", type=Path, default=C.TAXONOMY)
    ap.add_argument("--model", default=DEFAULT_MODEL)
    ap.add_argument("--batch-size", type=int, default=50)
    ap.add_argument("--concurrency", type=int, default=MAX_CONCURRENCY)
    ap.add_argument("--max-requests", type=int, default=0, help="hard request budget (required for a live run)")
    ap.add_argument("--max-errors", type=int, default=5, help="stop after this many consecutive failed batches")
    ap.add_argument("--codes", type=Path, help="only these item_codes (one per line), e.g. a pilot sample")
    ap.add_argument("--hide-gs1", action="store_true", help="do not send the GS1 group (pilot benchmark)")
    ap.add_argument("--effort", default="", choices=["", "low", "medium", "high"],
                    help='"" = thinking off (default); else adaptive thinking at this effort')
    ap.add_argument("--dry-run", action="store_true", help="select and build the requests, no API call")
    ap.add_argument("--write-labels", type=Path, help="write the checkpoint as an ai_labels CSV and exit")
    a = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    if a.write_labels:
        print(f"wrote {write_labels(a.work_dir, a.write_labels)} labels to {a.write_labels}")
        return 0
    if not (a.predictions and a.export):
        ap.error("--predictions and --export are required for a run")
    tax = C.load_taxonomy(a.taxonomy)
    export = {r["item_code"]: r for r in C.read_export(a.export)}
    rows = select_items(C.read_export(a.predictions), export)
    if a.codes:
        want = [c.strip() for c in a.codes.read_text(encoding="utf-8").split() if c.strip()]
        keep = set(want)
        rows = [r for r in rows if r["item_code"] in keep]
    rows.sort(key=lambda r: _md5(r["item_code"]))
    n_req = -(-len(rows) // a.batch_size)
    sys_chars = len(system_prompt(tax))
    print(json.dumps({"items": len(rows), "requests": n_req, "system_prompt_chars": sys_chars,
                      "model": a.model, "hide_gs1": a.hide_gs1}, ensure_ascii=False))
    if a.dry_run:
        sample = [{"i": i, **item_payload(r, a.hide_gs1)} for i, r in enumerate(rows[:3])]
        print(json.dumps(sample, ensure_ascii=False))
        return 0
    if a.max_requests <= 0:
        raise SystemExit("--max-requests is required for a live run (hard budget)")
    client = make_client()
    summary = run(rows, a.work_dir, client, a.model, tax, a.batch_size, a.concurrency, a.max_requests,
                  a.max_errors, a.hide_gs1, max_tokens=16000 if a.effort else 8000, effort=a.effort)
    print(json.dumps(summary, indent=1))
    return 0 if not summary["stopped"].endswith("errors") else 2


if __name__ == "__main__":
    raise SystemExit(main())
