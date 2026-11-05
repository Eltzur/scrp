"""SU11A-66 read-only category coverage report (Part A, for the browse design in
docs/catalog/su11a66_categories_browse_design.md).

Sections (each prints its own timing):
  a. live universe: search_items rows (the live build), hidden pseudo rows
     (coupons / service rows) and still-nameless rows; the same for popular
     items (sold by >= 3 and >= 5 chains);
  b. coverage of live items under the SU11A-57 display rule (high / medium
     show their node, low shows the department only): usable at category,
     department-only, none; by winning source and confidence; for all, >= 3
     and >= 5 chains;
  c. per department (all 16): live items, % usable at category, % usable at
     sub-category, % department-only, the top 5 categories by item count;
     plus the items with no label (no department);
  d. browse-page health: categories and sub-categories with 0, 1-4, 5-19 and
     more than 2,000 usable live items (listed with counts);
  e. flow: item_categories rows written per day over 14 days by source (the
     14:30 build writes rule / gs1 rows for NEW barcodes; an import also
     writes rule / gs1 / ai rows, so a day with an import counts both);
     open user category suggestions (counts only); manual and reviewed rows;
  f. quality from the repo files docs/catalog/review_graded_v1.csv and
     ai_audit_graded_v1.csv (no database): error rate by source and
     confidence, exact id / department / "shown wrong" under the display rule;
     departments with the most errors;
  g. alcohol (D10 except D10.C05) and tobacco (D10.C05) live items, by
     confidence: the size of the parked hide switch.

READ ONLY: SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY and
statement_timeout 120 s. Reads search_items, categories, item_categories and
category_suggestions (counts only, no user ids, no comments). Prints counts,
category ids / names and nothing about users. Expected total: well under 3 min
(search_items and item_categories are about 130k rows each).

Server (as dude, quiet time not needed):
    cd ~/scrp && ( ulimit -v 2000000; set -a; source .env; set +a; \
        venv/bin/python3 -m scripts.su11a66_category_coverage ) 2>&1 | tee ~/su11a66_coverage.txt

    --only a,b,f   run some sections only
    --files-only   section f only (no database; works on Windows too)
"""
from __future__ import annotations

import argparse
import csv
import time
from collections import Counter, defaultdict
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
REVIEW_CSV = ROOT / "docs" / "catalog" / "review_graded_v1.csv"
AI_AUDIT_CSV = ROOT / "docs" / "catalog" / "ai_audit_graded_v1.csv"
TIMEOUT = "120s"
POPULAR = (3, 5)
THIN_BUCKETS = ((0, 0, "0"), (1, 4, "1-4"), (5, 19, "5-19"))
FAT = 2000
TOBACCO = "D10.C05"


def pct(n: int, d: int) -> str:
    return f"{100.0 * n / d:5.1f}%" if d else "    -"


def dept(cid: str | None) -> str:
    return (cid or "").split(".")[0]


def level_of(cid: str | None) -> int:
    return 0 if not cid else cid.count(".") + 1


# ---------------------------------------------------------------- the per-item view
# One row per live, non-pseudo search_items barcode with its label (if any).
# shown_level: what the SU11A-57 display rule lets a user see (0 none,
# 1 department, 2 category, 3 sub-category). A label whose node is missing or
# inactive is counted as such, not as usable.
LIVE_SQL = """
SELECT si.item_code, si.chains_live, (si.name_norm = '') AS nameless,
       ic.category_id, ic.confidence, ic.source, ic.reviewed,
       c.level AS node_level, c.active AS node_active
FROM search_items si
LEFT JOIN item_categories ic ON ic.item_code = si.item_code
LEFT JOIN categories c ON c.id = ic.category_id
WHERE NOT si.is_pseudo AND si.chains_live >= 1
"""


def shown_level(r) -> int:
    if r["category_id"] is None:
        return 0
    if not r["node_active"]:
        return -1  # label on a missing / inactive node
    if r["confidence"] == "low":
        return 1
    return int(r["node_level"])


class Report:
    def __init__(self, conn, text):
        self.conn, self.text = conn, text
        self._live = None
        self._nodes = None

    def q(self, sql, **p):
        return self.conn.execute(self.text(sql), p).mappings().all()

    def exists(self, name: str) -> bool:
        return self.conn.execute(self.text("SELECT to_regclass(:n) IS NOT NULL"), {"n": name}).scalar()

    @property
    def live(self):
        if self._live is None:
            self._live = [dict(r) for r in self.q(LIVE_SQL)]
            for r in self._live:
                r["shown"] = shown_level(r)
        return self._live

    @property
    def nodes(self):
        if self._nodes is None:
            self._nodes = {r["id"]: dict(r) for r in self.q(
                "SELECT id, parent_id, level, name_he, name_en, active FROM categories ORDER BY sort_order, id")}
        return self._nodes

    def name(self, cid: str) -> str:
        n = self.nodes.get(cid)
        if not n:
            return f"{cid} (unknown)"
        return f"{cid} {n['name_he']}" + (f" ({n['name_en']})" if n["name_en"] else "")

    # ------------------------------------------------------------ a
    def a(self):
        built = self.q("SELECT max(built_at) AS b, count(*) AS n FROM search_items")[0]
        hidden = self.q("""
            SELECT count(*) FILTER (WHERE is_pseudo) AS pseudo,
                   count(*) FILTER (WHERE NOT is_pseudo AND name_norm = '') AS nameless,
                   count(*) FILTER (WHERE chains_live = 0) AS no_chain
            FROM search_items""")[0]
        print(f"  search build: built_at {built['b']}, {built['n']} rows in search_items")
        print(f"  hidden pseudo rows (coupons / service rows, is_pseudo): {hidden['pseudo']}")
        print(f"  rows with chains_live = 0: {hidden['no_chain']}")
        live = self.live
        print(f"  LIVE universe (not pseudo, chains_live >= 1): {len(live)}"
              f"  of which still nameless (name_norm empty): {sum(r['nameless'] for r in live)}")
        for k in POPULAR:
            sub = [r for r in live if r["chains_live"] >= k]
            print(f"  popular, >= {k} chains: {len(sub)} ({pct(len(sub), len(live)).strip()} of live)")
        dist = Counter(min(r["chains_live"], 10) for r in live)
        print("  chains_live distribution: " + ", ".join(
            f"{k}{'+' if k == 10 else ''}: {dist[k]}" for k in sorted(dist)))

    # ------------------------------------------------------------ b
    def _coverage(self, rows, title):
        n = len(rows)
        c = Counter(r["shown"] for r in rows)
        usable_cat = c[2] + c[3]
        print(f"  {title}: {n} items")
        print(f"    usable at category or deeper (high/medium, level 2-3): {usable_cat:>7} {pct(usable_cat, n)}")
        print(f"      of which at sub-category (level 3):                 {c[3]:>7} {pct(c[3], n)}")
        print(f"    department only (low, or a department-level label):  {c[1]:>7} {pct(c[1], n)}")
        print(f"    none (no label):                                      {c[0]:>7} {pct(c[0], n)}")
        if c[-1]:
            print(f"    label on a missing / inactive node:                   {c[-1]:>7} {pct(c[-1], n)}")

    def b(self):
        live = self.live
        self._coverage(live, "all live")
        for k in POPULAR:
            self._coverage([r for r in live if r["chains_live"] >= k], f">= {k} chains")
        print("  winning source x confidence (live items with a label; shown = what users see):")
        by = Counter((r["source"], r["confidence"], r["shown"]) for r in live if r["category_id"])
        tot = Counter((r["source"], r["confidence"]) for r in live if r["category_id"])
        print(f"    {'source':<7} {'conf':<7} {'items':>7} {'%live':>7}  shown: dept / cat / sub")
        for (s, cf), n in sorted(tot.items(), key=lambda kv: (kv[0][0], ["high", "medium", "low"].index(kv[0][1]))):
            print(f"    {s:<7} {cf:<7} {n:>7} {pct(n, len(live))}   {by[(s, cf, 1)]} / {by[(s, cf, 2)]} / {by[(s, cf, 3)]}")
        for k in POPULAR:
            sub = [r for r in live if r["chains_live"] >= k and r["category_id"]]
            t = Counter((r["source"], r["confidence"]) for r in sub)
            print(f"    >= {k} chains: " + ", ".join(f"{s}/{cf} {n}" for (s, cf), n in sorted(t.items())))

    # ------------------------------------------------------------ c
    def c(self):
        live = self.live
        depts = [n for n in self.nodes.values() if n["level"] == 1]
        per = defaultdict(list)
        for r in live:
            if r["category_id"]:
                per[dept(r["category_id"])].append(r)
        has_sub = {n["parent_id"] for n in self.nodes.values() if n["level"] == 3 and n["active"]}
        print(f"  {'dept':<4} {'items':>6} {'cat%':>7} {'sub%':>7} {'subable%':>9} {'dept-only%':>10}  name")
        for d in depts:
            rows = per.get(d["id"], [])
            n = len(rows)
            c = Counter(r["shown"] for r in rows)
            # items whose category HAS sub-types: what share reach one
            in_sub_cats = [r for r in rows if r["shown"] >= 2 and ".".join(r["category_id"].split(".")[:2]) in has_sub]
            sub_ok = sum(1 for r in in_sub_cats if r["shown"] == 3)
            print(f"  {d['id']:<4} {n:>6} {pct(c[2] + c[3], n)} {pct(c[3], n)} "
                  f"{pct(sub_ok, len(in_sub_cats)):>9} {pct(c[1], n):>10}  {self.name(d['id']).split(' ', 1)[1]}")
        nolab = sum(1 for r in live if not r["category_id"])
        print(f"  none (no label, no department): {nolab} {pct(nolab, len(live)).strip()}")
        print("  sub% = usable at sub-category of all the department's items; subable% = the same, of the")
        print("  usable items whose category has sub-types (only 35 nodes are sub-types)")
        print("  top 5 categories per department (usable items, high/medium at the category or below):")
        for d in depts:
            cnt = Counter(".".join(r["category_id"].split(".")[:2]) for r in per.get(d["id"], []) if r["shown"] >= 2)
            top = ", ".join(f"{self.nodes.get(k, {}).get('name_he', k)} {v}" for k, v in cnt.most_common(5))
            print(f"    {d['id']}: {top or '-'}")

    # ------------------------------------------------------------ d
    def d(self):
        live = self.live
        usable = Counter()
        for r in live:
            if r["shown"] >= 2:
                parts = r["category_id"].split(".")
                usable[".".join(parts[:2])] += 1
                if len(parts) == 3:
                    usable[r["category_id"]] += 1
        dept_all = Counter(dept(r["category_id"]) for r in live if r["category_id"])
        for lvl, label in ((2, "categories"), (3, "sub-categories")):
            nodes = [n for n in self.nodes.values() if n["level"] == lvl and n["active"]]
            print(f"  {label}: {len(nodes)} active")
            for lo, hi, b in THIN_BUCKETS:
                hit = sorted((usable[n["id"]], n["id"]) for n in nodes if lo <= usable[n["id"]] <= hi)
                print(f"    {b} usable live items: {len(hit)}")
                for v, i in hit:
                    print(f"      {v:>3}  {self.name(i)}")
            fat = sorted(((usable[n["id"]], n["id"]) for n in nodes if usable[n["id"]] > FAT), reverse=True)
            print(f"    more than {FAT}: {len(fat)}")
            for v, i in fat:
                print(f"      {v:>6}  {self.name(i)}")
        print("  departments (every label, low included - a department page may show low labels):")
        for d in [n for n in self.nodes.values() if n["level"] == 1]:
            print(f"    {d['id']:<4} {dept_all[d['id']]:>6}  {d['name_he']}")

    # ------------------------------------------------------------ e
    def e(self):
        rows = self.q("""
            SELECT (decided_at AT TIME ZONE 'Asia/Jerusalem')::date AS day, source, count(*) AS n
            FROM item_categories
            WHERE decided_at >= now() - interval '14 days'
            GROUP BY 1, 2 ORDER BY 1, 2""")
        print("  item_categories rows by decided_at day (Israel), last 14 days. The build writes")
        print("  rule / gs1 rows for new barcodes only; an import or admin edit also moves decided_at,")
        print("  so a day with an import shows the import too. Nothing else records the build's own count")
        print("  (its JSON goes to: journalctl -u scrp-search-items | grep item_categories).")
        days = defaultdict(Counter)
        for r in rows:
            days[r["day"]][r["source"]] = r["n"]
        if not days:
            print("    (no rows in the last 14 days)")
        for day in sorted(days):
            c = days[day]
            print(f"    {day}: " + ", ".join(f"{s} {c[s]}" for s in ("rule", "gs1", "ai", "manual") if c[s]))
        unl = sum(1 for r in self.live if not r["category_id"])
        print(f"  live items with no label today: {unl} (the build could not classify them, or they are older)")
        man = self.q("""
            SELECT count(*) FILTER (WHERE source = 'manual') AS manual,
                   count(*) FILTER (WHERE reviewed) AS reviewed,
                   count(*) FILTER (WHERE reviewed AND source <> 'manual') AS reviewed_not_manual,
                   count(*) AS all_rows
            FROM item_categories""")[0]
        print(f"  item_categories rows: {man['all_rows']}; manual {man['manual']}; reviewed {man['reviewed']}"
              f" (reviewed but not manual: {man['reviewed_not_manual']})")
        if self.exists("public.category_suggestions"):
            s = self.q("""
                SELECT count(*) FILTER (WHERE status = 'open') AS open,
                       count(*) FILTER (WHERE status = 'accepted') AS accepted,
                       count(*) FILTER (WHERE status = 'rejected') AS rejected,
                       count(*) FILTER (WHERE status = 'open' AND created_at < now() - interval '7 days') AS open_7d,
                       count(DISTINCT item_code) FILTER (WHERE status = 'open') AS open_items
                FROM category_suggestions""")[0]
            print(f"  user category suggestions: open {s['open']} (on {s['open_items']} items; older than 7 days"
                  f" {s['open_7d']}), accepted {s['accepted']}, rejected {s['rejected']}")
        else:
            print("  user category suggestions: table missing (su11a57 not applied)")

    # ------------------------------------------------------------ g
    def g(self):
        rows = [r for r in self.live if dept(r["category_id"]) == "D10"]
        tob = [r for r in rows if (r["category_id"] or "").startswith(TOBACCO)]
        alc = [r for r in rows if not (r["category_id"] or "").startswith(TOBACCO)]
        for title, sub in (("alcohol (D10 except D10.C05)", alc), ("tobacco (D10.C05)", tob)):
            c = Counter(r["confidence"] for r in sub)
            pop = sum(1 for r in sub if r["chains_live"] >= 3)
            print(f"  {title}: {len(sub)} live items (high {c['high']}, medium {c['medium']}, low {c['low']});"
                  f" >= 3 chains {pop}")
        d10 = Counter(r["category_id"] for r in rows if r["confidence"] != "low")
        print("  by node (high/medium): " + ", ".join(f"{k} {v}" for k, v in sorted(d10.items())))
        print("  Low-confidence labels elsewhere can still be alcohol / tobacco; a hide switch on D10")
        print("  hides labelled items only.")


# ---------------------------------------------------------------- f (files only)
def _shown(cid: str, conf: str) -> str:
    return dept(cid) if conf == "low" else cid


def _is_prefix(shown: str, correct: str) -> bool:
    return correct == shown or correct.startswith(shown + ".")


def quality() -> None:
    rows = []
    for r in csv.DictReader(REVIEW_CSV.open(encoding="utf-8-sig")):
        rows.append({"file": "review", "pred": r["predicted_category_id"], "correct": r["correct_category_id"],
                     "source": r["source"] or "none", "conf": r["confidence"], "stratum": r["stratum"]})
    for r in csv.DictReader(AI_AUDIT_CSV.open(encoding="utf-8-sig")):
        rows.append({"file": "ai_audit", "pred": r["ai_category_id"], "correct": r["correct_category_id"],
                     "source": "ai", "conf": r["confidence"], "stratum": "ai_only"})
    rows = [r for r in rows if r["correct"]]
    print(f"  graded rows: review_graded_v1 {sum(r['file'] == 'review' for r in rows)} (100 top-chain + 50 random;"
          f" labels as of v1, before the v1.1 fixes these rows informed), ai_audit_graded_v1"
          f" {sum(r['file'] == 'ai_audit' for r in rows)} (AI-only labels, 34/33/33 by confidence)")
    print("  exact = predicted id differs; dept = department differs; shown wrong = what the SU11A-57 rule")
    print("  shows (low: the department) is not the correct node or one of its ancestors")
    print(f"    {'file':<9} {'source':<7} {'conf':<12} {'n':>4} {'exact':>7} {'dept':>7} {'shown wrong':>12}")
    groups = defaultdict(list)
    for r in rows:
        groups[(r["file"], r["source"], r["conf"])].append(r)
    for (f, s, cf), g in sorted(groups.items()):
        n = len(g)
        ex = sum(r["pred"] != r["correct"] for r in g)
        de = sum(dept(r["pred"]) != dept(r["correct"]) for r in g)
        sw = sum(bool(r["pred"]) and not _is_prefix(_shown(r["pred"], r["conf"]), r["correct"]) for r in g)
        print(f"    {f:<9} {s:<7} {cf:<12} {n:>4} {pct(ex, n):>7} {pct(de, n):>7} {pct(sw, n):>12}")
    for f in ("review", "ai_audit"):
        g = [r for r in rows if r["file"] == f]
        sw = sum(bool(r["pred"]) and not _is_prefix(_shown(r["pred"], r["conf"]), r["correct"]) for r in g)
        print(f"    {f:<9} all: exact {pct(sum(r['pred'] != r['correct'] for r in g), len(g)).strip()},"
              f" shown wrong {pct(sw, len(g)).strip()}")
    errs = Counter(dept(r["correct"]) for r in rows if r["pred"] != r["correct"])
    alln = Counter(dept(r["correct"]) for r in rows)
    print("  departments with the most exact-id errors (by the CORRECT department): " + ", ".join(
        f"{d} {n}/{alln[d]}" for d, n in errs.most_common(8)))
    moves = Counter((dept(r["pred"]), dept(r["correct"])) for r in rows
                    if r["pred"] and dept(r["pred"]) != dept(r["correct"]))
    print("  department moves (predicted -> correct): " + ", ".join(
        f"{a}->{b} {n}" for (a, b), n in moves.most_common(10)))


SECTIONS = ("a", "b", "c", "d", "e", "f", "g")
TITLES = {"a": "live universe", "b": "coverage of live items", "c": "per department",
          "d": "browse-page health", "e": "flow", "f": "quality (repo files)", "g": "alcohol and tobacco"}


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--only", default=",".join(SECTIONS), help="comma-separated sections (default: all)")
    ap.add_argument("--files-only", action="store_true", help="section f only, no database")
    a = ap.parse_args()
    want = ["f"] if a.files_only else [s.strip() for s in a.only.split(",") if s.strip() in SECTIONS]
    t_all = time.monotonic()
    rep = None
    conn = None
    if any(s != "f" for s in want):
        from sqlalchemy import text
        from db.db import connect
        conn = connect()
        conn.execute(text("SET SESSION CHARACTERISTICS AS TRANSACTION READ ONLY"))
        conn.execute(text(f"SET statement_timeout = '{TIMEOUT}'"))
        conn.commit()
        conn.execute(text("SET TRANSACTION READ ONLY"))
        rep = Report(conn, text)
        missing = [t for t in ("public.search_items", "public.categories", "public.item_categories")
                   if not rep.exists(t)]
        if missing:
            raise SystemExit(f"missing tables: {missing} (su11a36 / su11a52 not applied?)")
    try:
        for s in want:
            t0 = time.monotonic()
            print(f"\n== {s}. {TITLES[s]}")
            if s == "f":
                quality()
            else:
                getattr(rep, s)()
            print(f"  [{s}: {time.monotonic() - t0:.1f} s]")
    finally:
        if conn is not None:
            conn.rollback()
            conn.close()
    print(f"\n== total {time.monotonic() - t_all:.1f} s")


if __name__ == "__main__":
    main()
