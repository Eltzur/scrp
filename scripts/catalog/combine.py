"""Combine rule / GS1 labels with AI labels into the final v1 labels (SU11A-52).

    python -m scripts.catalog.combine --predictions RUN/predictions.csv.gz \\
        --export EXPORT.csv.gz --ai docs/catalog/ai_labels_v1.csv --out-dir OUT \\
        [--disagreements docs/catalog/disagreements_v1.csv] [--review-sample docs/catalog/review_sample_v1.csv]

The same combine_label() is used by scripts/catalog/import_categories.py on the
server, so the local report and the imported rows follow one rule:

  rule / gs1 result      AI result               final
  high                   (any)                   rule / gs1 as is (AI is not asked)
  low or unclassified    high or medium          AI (source ai, AI's confidence)
  unclassified           low                     AI at low
  medium                 high / medium, same     the deeper of the two ids, high
                         lineage                 (source of the id that is used)
  medium                 high / medium, sibling  the shared category id, high
                         sub-type of the same
                         category
  medium                 high / medium, other    DISAGREEMENT: low; the AI id when the
                         lineage                 AI is high, else the rule id; listed in
                                                 disagreements_v1.csv
  low / medium           low                     rule / gs1 as is
  (any)                  none / "unknown"        rule / gs1 as is (unclassified stays so)
  pinned brand dept      outside that department rule / gs1 as is (SU11A-55: טבעול is frozen)
Storage split (SU11A-56): with rule["storage"] == "shelf", a pickle / olive id D04.C05 (the
rule's or the AI's) is read as D07.C08.S01, before the comparison above.

source: gs1 when the GS1 group decided or confirmed the rule result (reason gs1
or rule+gs1), rule otherwise (rule / brand / prior), ai for AI ids.
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import sys
from collections import Counter
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

import scripts.catalog.classify_rules as C  # noqa: E402
from db.search_norm import normalize, pseudo_pattern  # noqa: E402

UNKNOWN = "unknown"


def rule_source(reason: str) -> str:
    return "gs1" if reason in ("gs1", "rule+gs1") else "rule"


def _depth(nid: str) -> int:
    return nid.count(".")


def _category(nid: str) -> str:
    return ".".join(nid.split(".")[:2])


def combine_label(rule: dict, ai: dict | None, valid_ids: set[str] | None = None) -> dict | None:
    """Final label for one item, or None when it stays unclassified.

    rule: category_id, confidence ('' = unclassified), reason, keyword (and
    optionally gs1_group, pinned). ai: category_id, confidence, reason, model, or None.
    """
    rid, rconf = rule.get("category_id") or "", rule.get("confidence") or ""
    src = rule_source(rule.get("reason") or "")
    detail = (rule.get("reason") or "") + (f": {rule['keyword']}" if rule.get("keyword") else "")
    if src == "gs1" and rule.get("gs1_group"):
        detail += f" | gs1: {rule['gs1_group']}"
    base = ({"category_id": rid, "confidence": rconf, "source": src, "detail": detail[:300], "model": None,
             "disagreement": False, "ai_category_id": "", "rule_category_id": rid} if rid else None)
    aid = (ai or {}).get("category_id") or ""
    if valid_ids is not None:
        aid = C.split_storage(aid, rule.get("storage") or "", valid_ids)
    if not aid or aid == UNKNOWN or (valid_ids is not None and aid not in valid_ids) or rconf == "high":
        return base
    if rule.get("pinned") and aid.split(".")[0] != rule["pinned"]:
        return base
    aconf, model = ai.get("confidence") or "low", ai.get("model") or None
    adetail = f"ai: {ai.get('reason') or ''}".strip()
    as_ai = {"category_id": aid, "confidence": aconf, "source": "ai", "detail": adetail[:300], "model": model,
             "disagreement": False, "ai_category_id": aid, "rule_category_id": rid}
    if aconf == "low":
        return as_ai if not rid else {**base, "ai_category_id": aid}
    if rconf in ("", "low"):
        return as_ai
    # rule medium, AI high / medium
    if C.related(rid, aid):
        if _depth(aid) > _depth(rid):
            return {**as_ai, "confidence": "high", "detail": f"{adetail} | agrees with {src} {rid}"[:300]}
        return {**base, "confidence": "high", "detail": f"{detail} | ai agrees ({aid})"[:300], "ai_category_id": aid}
    cat = _category(rid)
    if cat == _category(aid) and "." in cat:
        # sibling sub-types of one category: both agree on the category
        return {**base, "category_id": cat, "confidence": "high",
                "detail": f"{detail} | ai agrees on the category ({aid})"[:300], "ai_category_id": aid}
    if aconf == "high":
        return {**as_ai, "confidence": "low", "disagreement": True,
                "detail": f"{adetail} | DISAGREES with {src} {rid}"[:300]}
    return {**base, "confidence": "low", "disagreement": True, "ai_category_id": aid,
            "detail": f"{detail} | DISAGREES with ai {aid}"[:300]}


def _w(r: dict) -> int:
    try:
        return max(1, int(r.get("chains_live") or 1))
    except ValueError:
        return 1


def coverage(rows: list[dict], final: list[dict | None]) -> dict:
    cnt, wcnt, src = Counter(), Counter(), Counter()
    for r, f in zip(rows, final):
        k = f["confidence"] if f else "unclassified"
        cnt[k] += 1
        wcnt[k] += _w(r)
        if f:
            src[f"{f['source']}/{f['confidence']}"] += 1
    tot, wtot = sum(cnt.values()) or 1, sum(wcnt.values()) or 1
    return {"items": sum(cnt.values()),
            "by_confidence": {k: {"items": cnt[k], "pct": round(100 * cnt[k] / tot, 1),
                                  "weighted_pct": round(100 * wcnt[k] / wtot, 1)}
                              for k in ("high", "medium", "low", "unclassified")},
            "by_source_confidence": dict(sorted(src.items()))}


def _md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--predictions", required=True, type=Path)
    ap.add_argument("--export", required=True, type=Path)
    ap.add_argument("--ai", required=True, type=Path)
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--disagreements", type=Path)
    ap.add_argument("--review-sample", type=Path)
    a = ap.parse_args(argv)
    for stream in (sys.stdout, sys.stderr):
        stream.reconfigure(encoding="utf-8")
    tax = C.load_taxonomy()
    valid = set(tax.nodes)
    export = {r["item_code"]: r for r in C.read_export(a.export)}
    pred = C.read_export(a.predictions)
    with open(a.ai, encoding="utf-8", newline="") as fh:
        ai = {r["item_code"]: r for r in csv.DictReader(fh)}
    rows, final, rule_only, pseudo = [], [], [], 0
    by_code = {p["item_code"]: p for p in pred}
    for p in pred:
        r = export[p["item_code"]]
        if pseudo_pattern(normalize(C.item_name(r))):
            pseudo += 1          # hidden by the SU11A-52 service rule: no category
            continue
        rows.append(r)
        rule = {**p, "gs1_group": r.get("gs1_group")}
        final.append(combine_label(rule, ai.get(p["item_code"]), valid))
        rule_only.append(combine_label(rule, None, valid))
    rep = {"pseudo_service_rows_excluded": pseudo, "ai_labels": len(ai),
           "ai_labels_unknown": sum(1 for x in ai.values() if x["category_id"] == UNKNOWN),
           "rules_gs1": coverage(rows, rule_only), "final": coverage(rows, final)}
    dis = [(r, f) for r, f in zip(rows, final) if f and f["disagreement"]]
    pat = Counter()
    for r, f in dis:
        pat[(tax.category_of(f["rule_category_id"]), tax.category_of(f["ai_category_id"]))] += 1
    rep["disagreements"] = {"items": len(dis), "top_patterns": [
        {"rule": k[0], "ai": k[1], "n": n, "rule_he": tax.path_he(k[0]), "ai_he": tax.path_he(k[1])}
        for k, n in pat.most_common(25)]}
    a.out_dir.mkdir(parents=True, exist_ok=True)
    with gzip.open(a.out_dir / "final_labels_v1.csv.gz", "wt", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["item_code", "name", "category_id", "path_he", "confidence", "source", "detail", "model",
                    "chains_live"])
        for r, f in zip(rows, final):
            if f:
                w.writerow([r["item_code"], C.item_name(r), f["category_id"], tax.path_he(f["category_id"]),
                            f["confidence"], f["source"], f["detail"], f["model"] or "", r.get("chains_live", "")])
    (a.out_dir / "combine_report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    if a.disagreements:
        top = sorted(dis, key=lambda x: (-_w(x[0]), x[0]["item_code"]))[:300]
        with open(a.disagreements, "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(["item_code", "name", "chains_live", "gs1_group", "rule_category_id", "rule_path_he",
                        "rule_source", "ai_category_id", "ai_path_he", "ai_confidence", "ai_reason",
                        "final_category_id", "correct_category_id"])
            for r, f in top:
                p = by_code[r["item_code"]]
                x = ai[r["item_code"]]
                w.writerow([r["item_code"], C.item_name(r), r.get("chains_live", ""), r.get("gs1_group", ""),
                            p["category_id"], tax.path_he(p["category_id"]), rule_source(p["reason"]),
                            x["category_id"], tax.path_he(x["category_id"]), x["confidence"], x["reason"],
                            f["category_id"], ""])
    if a.review_sample:
        idx = sorted(range(len(rows)), key=lambda i: (-_w(rows[i]), _md5(rows[i]["item_code"])))
        top = idx[:100]
        rest = sorted(idx[100:], key=lambda i: _md5("su11a52" + rows[i]["item_code"]))[:50]
        with open(a.review_sample, "w", encoding="utf-8", newline="") as fh:
            w = csv.writer(fh, lineterminator="\n")
            w.writerow(["item_code", "name", "manufacturer", "gs1_group", "chains_live", "stratum",
                        "predicted_category_id", "predicted_path_he", "source", "confidence", "detail",
                        "correct_category_id"])
            for stratum, part in (("top_chains", top), ("random", rest)):
                for i in part:
                    r, f = rows[i], final[i]
                    w.writerow([r["item_code"], C.item_name(r), r.get("manufacturer", ""), r.get("gs1_group", ""),
                                r.get("chains_live", ""), stratum, f["category_id"] if f else "",
                                tax.path_he(f["category_id"]) if f else "", f["source"] if f else "",
                                f["confidence"] if f else "unclassified", f["detail"] if f else "", ""])
    print(json.dumps(rep, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
