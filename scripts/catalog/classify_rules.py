"""Rule-based catalogue classifier (SU11A-51, v1 in SU11A-52). Offline: reads a
local export, writes local files, never touches a database. The same functions
classify new barcodes in scripts/build_search_items.py (SU11A-52).

    python -m scripts.catalog.classify_rules --input EXPORT.csv.gz --out-dir DIR \
        [--review-sample docs/catalog/review_sample_v1.csv] [--no-gs1] \
        [--taxonomy docs/catalog/taxonomy_v0.csv --gs1-map ... --brand-hints ""]

Input: the SU11A-51 export (one row per live, non-pseudo search_items row; columns
item_code, name, manufacturer, manufacturer_norm, chains_live, gs1_group, gs1_brand,
gs1_kosher, gs1_diet, is_weighted, ...). Output in DIR: predictions.csv.gz (one row
per item), report.json and report.txt (evaluation), unclassified_leading.tsv.

Rules come from docs/catalog/taxonomy_v1_2.csv (keywords_he / negative_keywords_he),
docs/catalog/gs1_group_map_v1_2.csv and docs/catalog/brand_category_hints_v1_1.csv
(v1.1, SU11A-55: same node ids as taxonomy_v1.csv, fixed keywords; v1.2, SU11A-56: three
nodes added; v1 and v1.1 kept as the record). Pickles and olives are split by storage
evidence after classification (storage_of / split_storage: deli D04.C05, shelf-stable
D07.C08.S01); row_features() adds §weighed / §import from the barcode and is_weighted.
Names are normalised with db.search_norm.

Keyword grammar (one keyword per '|' item, matched on whole tokens):
  - "a b"      a phrase: consecutive tokens a then b
  - "a*"       token prefix: a token starting with a (מיובש* = מיובש, מיובשת, ...)
  - "x,y+z"    conjunction: one of the comma alternatives of every '+' part must
               occur somewhere in the name (צלחות,כוסות+חד פעמי*,פלסטיק)
  - "^a"       head anchor (SU11A-55): the phrase counts only as the first content
               word of the name ("^אפרסק" matches "אפרסק צהוב", not "פרוטאין אפרסק")
  - "§pct"     feature token (SU11A-55): the name has a percentage (3%, 1.6 %);
               used inside conjunctions ("פרוטאין+§pct")
Negatives use the same grammar; a negative of a node (or of any ancestor) that
occurs anywhere in the name vetoes that node. A GS1-only negative ("~ספרינג",
SU11A-56) does not stop keywords; it only refuses the node when the GS1 group map
proposes it (Spring is a still fruit drink even in the GS1 juice group). A hard negative ("!רסק", SU11A-55)
also refuses the node when the GS1 group map proposes it: "רסק תפוחים" in the
GS1 group Apples is not fresh fruit. Plain negatives only stop keyword matches
(they were written for that, and many GS1 rows are right where they would veto).

Precedence: matches before a connector word (עם, בטעם, ללא ...) beat matches
after it; then the earliest content position (pack words such as מארז / סט /
שישיית, numbers and units are not counted); then the longer keyword (tokens);
then the deeper node. Within the winning category the deepest matching
sub-type is reported.

Confidence: high = the winning match is in the first two content words and no
other category matched before a connector; medium = it won on position or
length against another category, or matched later in the name; low = a tie with
another category (position and length equal) or only matched after a connector.
GS1 (unless --no-gs1): a mapped group that agrees with the rule (same lineage)
-> the deeper id, high, reason rule+gs1; no rule match -> the GS1 id (high when
the map row is high, else medium); a disagreement with a high map row -> the
GS1 id at medium. Manufacturer priors are used only to break ties.

Brand hints (SU11A-52, docs/catalog/brand_category_hints_v1.csv): when a hinted
brand occurs in the name (as the first content word for position=first,
anywhere for position=any):
  - the plain rule result stands when it is already in the brand's department
    (the brand may itself be a keyword: לנור, האגיס);
  - otherwise the brand's words are removed and the rules run on the rest, so a
    brand word cannot fire as a keyword elsewhere (שמיר is a hummus brand, not
    dill; טבע דלי is not a bucket);
  - when neither matches and the hint has fallback=yes, the brand's category is
    used (reason "brand", at most medium);
  - a name that is only the brand word keeps the plain rule result.
A hint with pin=yes (SU11A-55: טבעול is a frozen-food brand) pins the department:
a rule result outside it is replaced by the best match among that department's
nodes, else the hint's category; neither a GS1 group nor an AI label outside the
department can override it (Result.pinned).
"""
from __future__ import annotations

import argparse
import csv
import gzip
import hashlib
import json
import re
import sys
from collections import Counter, defaultdict
from dataclasses import dataclass, field, replace
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from db.search_norm import normalize  # noqa: E402

# v1.1 (SU11A-55): same 201 node ids as v1; keywords, negatives and brand hints changed.
# v1.2 (SU11A-56): every v1.1 id kept, three nodes added (D09.C11 still soft drinks,
# D16.C08 newspapers and magazines, D07.C08.S01 shelf-stable pickles and olives).
TAXONOMY_VERSION = "v1.2"
TAXONOMY = ROOT / "docs" / "catalog" / "taxonomy_v1_2.csv"
GS1_MAP = ROOT / "docs" / "catalog" / "gs1_group_map_v1_2.csv"
BRAND_HINTS = ROOT / "docs" / "catalog" / "brand_category_hints_v1_1.csv"

# Storage split (SU11A-56): a pickle / olive result (DELI_PICKLES) moves to the shelf-stable
# sub-type when the name (or the row) shows packed storage and nothing shows deli storage.
DELI_PICKLES, SHELF_PICKLES = "D04.C05", "D07.C08.S01"

_EDGE = "\"'.,;:!?()[]{}<>/\\|*+=#&@^~_%`"
# Pack / marketing words: they do not count as a content position.
SKIP_WORDS = frozenset(normalize(w) for w in """
מארז מארזי סט זוג זוגות צמד שלישיית שלישייה שלישית שלשיית רביעיית רביעייה רביעית רבעיית
חמישיית שישיית שישייה שישית מאגדת מגה מיני מבצע חדש חדשה ענק משפחתי פרימיום premium
מבחר מגוון יח יח' יחידות יחידה אריזת אריזה חבילת חבילה ק"ג קג גרם גר גר' ג ג' מ"ל מל
ליטר ל ל' ס"מ מ' x מבצע! חדש! במשקל
חצי רבע סלסלת סלסלה ארגז
""".split())
# Words that end the "head" of a name: what follows describes, not names, the product.
CONNECTORS = frozenset(normalize(w) for w in """
עם בטעם בטעמי במילוי בציפוי ברוטב בשמן במיץ בתוספת בניחוח בריח בסגנון בנוסח מבית של ללא
נטול נטולת על ב ל ו בתוך מועשר מועשרת בשילוב
""".split())
_NUM = re.compile(r"^[\d.,/*x×%-]+$")
# Prefix keywords compare with final letters unified (מעושן* must match מעושנת).
_FINALS = str.maketrans("ךםןףץ", "כמנפצ")


def unfinal(t: str) -> str:
    return t.translate(_FINALS)
CONF_ORDER = {"high": 0, "medium": 1, "low": 2, "": 3}


# --------------------------------------------------------------------------- text
_GLUE = re.compile(r"(?<=[א-ת])(?=\d)|(?<=\d)(?=[א-ת])")


def tokens(name: str) -> list[str]:
    """Normalised tokens with edge punctuation stripped; empty tokens dropped.

    Hebrew glued to a number is split first ("בחומץ560ג" -> "בחומץ 560 ג").
    """
    out = []
    for raw in _GLUE.sub(" ", normalize(name)).split(" "):
        t = raw.strip(_EDGE).replace(FEATURE, "")
        if t:
            out.append(t)
    return out


# Feature tokens (SU11A-55): facts about the whole name that the token grammar
# cannot see, appended after the real tokens so they never move a position.
FEATURE = "§"
_PCT_FEATURE = re.compile(r"(?<![\d.,])\d{1,3}(?:[.,]\d+)?\s?%")


def feature_tokens(name: str) -> list[str]:
    n = normalize(name)
    out = [FEATURE + "pct"] if _PCT_FEATURE.search(n) else []
    if parse_size(n):
        out.append(FEATURE + "size")     # a pack size with a unit (540 גרם, 1.5 ל, 3 ק"ג)
    return out


def row_features(item_code: str = "", is_weighted=None) -> list[str]:
    """Feature tokens from the row, not the name: §weighed for a weighed item or a store's
    own short code (7 digits or fewer: in-store packing, deli counter, produce); §import for
    a foreign GTIN (8+ digits not starting 729: imported goods travel ambient)."""
    code = (item_code or "").strip()
    if str(is_weighted or "") in ("1", "True", "true") or (code.isdigit() and len(code) <= 7):
        return [FEATURE + "weighed"]
    if code.isdigit() and len(code) >= 8 and not code.startswith("729"):
        return [FEATURE + "import"]
    return []


# Evidence for the storage split (normalised tokens / phrases).
_DELI_EVIDENCE = [tuple(normalize(p).split()) for p in """
§weighed|שקיל|שקילה|שקילים|במשקל|לפי משקל|לק"ג|תפזורת|מעדנייה|מעדניה|מעדני|דלי|בדלי|טרי|טריים|
ברדה|שמיר|צבר|אחלה|סלטי""".replace("\n", "").split("|") if p.strip()]
_SHELF_EVIDENCE = [tuple(normalize(p).split()) for p in """
§size|§import|צנצנת|בצנצנת|צנצנות|פחית|בפחית|פח|בפח|קופסה|בקופסה|קופסת|שימורי|שימורים|משומר|משומרים|
יכין|פרי הגליל|גפן|ויליפוד|זיתא|זאדונא|ולאסיק|יבנה|בית השיטה|מוטולה|דון פרננדו|איליאדה|סבא חביב|ביכורי השדה""".replace("\n", "").split("|") if p.strip()]


def _has(toks: list[str], phrases: list[tuple[str, ...]]) -> str:
    for ph in phrases:
        for i in range(len(toks) - len(ph) + 1):
            if tuple(toks[i:i + len(ph)]) == ph:
                return " ".join(ph)
    return ""


def storage_of(toks: list[str]) -> str:
    """"deli" when anything shows deli / weighed storage, else "shelf" when anything shows
    packed storage (a pack size, jar / can words, a shelf brand), else ""."""
    if _has(toks, _DELI_EVIDENCE):
        return "deli"
    return "shelf" if _has(toks, _SHELF_EVIDENCE) else ""


def split_storage(category_id: str, storage: str, valid) -> str:
    """D04.C05 -> D07.C08.S01 for shelf-stable pickles and olives (when the taxonomy has it)."""
    if category_id == DELI_PICKLES and storage == "shelf" and SHELF_PICKLES in valid:
        return SHELF_PICKLES
    return category_id


def is_content(t: str) -> bool:
    """A word that names something: not a pack word, a number or a feature token."""
    return t not in SKIP_WORDS and not _NUM.match(t) and not t.startswith(FEATURE)


def content_index(toks: list[str]) -> tuple[list[int], int]:
    """Per token: number of content tokens before it; and the head end index.

    Head = tokens before the first connector word (a connector at index 0 does
    not end the head: "על האש ..." still names the product).
    """
    eff, n, head_end = [], 0, len(toks)
    for i, t in enumerate(toks):
        eff.append(n)
        if head_end == len(toks) and i > 0 and t in CONNECTORS:
            head_end = i
        if is_content(t):
            n += 1
    return eff, head_end


# --------------------------------------------------------------------------- rules
@dataclass(frozen=True)
class Phrase:
    toks: tuple[tuple[str, bool], ...]  # (token, is_prefix)
    head: bool = False                  # "^": only as the first content word

    def match_at(self, toks: list[str], i: int) -> bool:
        if i + len(self.toks) > len(toks):
            return False
        for k, (t, pre) in enumerate(self.toks):
            w = toks[i + k]
            if not (unfinal(w).startswith(t) if pre else w == t):
                return False
        return True


@dataclass
class Rule:
    text: str
    node: str
    parts: list[list[Phrase]]
    negative: bool = False
    hard: bool = False               # "!": a negative that also refuses the GS1 id (SU11A-55)
    gs1_only: bool = False           # "~": refuses the GS1 id only, keywords still match (SU11A-56)

    @property
    def size(self) -> int:
        return sum(max(len(p.toks) for p in part) for part in self.parts)


def parse_phrase(s: str) -> Phrase | None:
    out = []
    s = s.strip()
    head = s.startswith("^")
    for t in normalize(s.lstrip("^")).split(" "):
        pre = t.endswith("*")
        t = t.rstrip("*").strip(_EDGE.replace("*", ""))
        if not t:
            continue
        pre = pre and len(t) >= 2
        out.append((unfinal(t) if pre else t, pre))
    return Phrase(tuple(out), head) if out else None


def parse_rule(text: str, node: str, negative: bool = False) -> Rule | None:
    parts = []
    hard = negative and text[:1] in "!~"
    gs1_only = negative and text.startswith("~")
    for part in text.lstrip("!~").split("+"):
        alts = [p for p in (parse_phrase(a) for a in part.split(",")) if p]
        if not alts:
            return None
        parts.append(alts)
    return Rule(text, node, parts, negative, hard, gs1_only) if parts else None


def match_rule(rule: Rule, toks: list[str], eff: list[int] | None = None) -> tuple[int, int] | None:
    """(start index, matched token count) of the rule in toks, or None.

    Single-part rule: the earliest occurrence (longest alternative there).
    Conjunction: every part must occur; start = earliest part occurrence.
    eff: content_index(toks)[0], for head-anchored ("^") phrases.
    """
    starts, size = [], 0
    for part in rule.parts:
        best = None
        for ph in part:
            if ph.head and eff is None:
                eff = content_index(toks)[0]
            for i in range(len(toks)):
                if ph.head and (eff[i] != 0 or not is_content(toks[i])):
                    continue
                if ph.match_at(toks, i):
                    cand = (i, -len(ph.toks))
                    if best is None or cand < best:
                        best = cand
                    break
        if best is None:
            return None
        starts.append(best[0])
        size += -best[1]
    return min(starts), size


@dataclass
class Node:
    id: str
    level: str
    parent: str
    name_he: str
    name_en: str
    attributes: list[str]
    depth: int


@dataclass
class Taxonomy:
    nodes: dict[str, Node]
    rules: list[Rule]
    negatives: list[Rule]
    exact: dict[str, list[int]] = field(default_factory=lambda: defaultdict(list))
    prefix: dict[str, list[int]] = field(default_factory=lambda: defaultdict(list))
    nexact: dict[str, list[int]] = field(default_factory=lambda: defaultdict(list))
    nprefix: dict[str, list[int]] = field(default_factory=lambda: defaultdict(list))

    def ancestors(self, nid: str) -> list[str]:
        out = []
        while nid:
            out.append(nid)
            nid = self.nodes[nid].parent
        return out

    def category_of(self, nid: str) -> str:
        """The category-level id (D.C) of a node; a department id stays as is."""
        p = nid.split(".")
        return ".".join(p[:2])

    def path_he(self, nid: str) -> str:
        return " > ".join(self.nodes[a].name_he for a in reversed(self.ancestors(nid)))

    def attrs_for(self, nid: str) -> list[str]:
        out = []
        for a in reversed(self.ancestors(nid)):
            out += [x for x in self.nodes[a].attributes if x not in out]
        return out

    def index(self) -> None:
        for coll, ex, pr in ((self.rules, self.exact, self.prefix), (self.negatives, self.nexact, self.nprefix)):
            for ri, r in enumerate(coll):
                for ph in r.parts[0]:
                    t, pre = ph.toks[0]
                    (pr if pre else ex)[t].append(ri)

    def candidates(self, toks: list[str], negative: bool = False) -> set[int]:
        ex, pr = (self.nexact, self.nprefix) if negative else (self.exact, self.prefix)
        out: set[int] = set()
        for t in toks:
            out.update(ex.get(t, ()))
            u = unfinal(t)
            for k in range(2, len(u) + 1):
                out.update(pr.get(u[:k], ()))
        return out


def load_taxonomy(path: Path = TAXONOMY) -> Taxonomy:
    nodes, rules, negs = {}, [], []
    with open(path, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            nid = row["id"]
            nodes[nid] = Node(nid, row["level"], row["parent_id"], row["name_he"], row["name_en"],
                              [a for a in row["attributes"].split("|") if a], nid.count(".") + 1)
            for kw in row["keywords_he"].split("|"):
                r = parse_rule(kw.strip(), nid) if kw.strip() else None
                if r:
                    rules.append(r)
            for kw in row["negative_keywords_he"].split("|"):
                r = parse_rule(kw.strip(), nid, negative=True) if kw.strip() else None
                if r:
                    negs.append(r)
    tax = Taxonomy(nodes, rules, negs)
    tax.index()
    return tax


@dataclass(frozen=True)
class BrandHint:
    brand: str                       # as written in the CSV (also the brand attribute)
    toks: tuple[str, ...]            # normalised tokens
    category_id: str
    confidence: str                  # high / medium / low; capped at medium when used
    first_only: bool
    fallback: bool = True            # use category_id when the rest of the name matches nothing
    pin: bool = False                # the brand pins the department (SU11A-55)


def load_brand_hints(path: Path | None = BRAND_HINTS) -> dict[str, list[BrandHint]]:
    """First token -> hints (longest brand first). Missing / empty path -> {}."""
    out: dict[str, list[BrandHint]] = defaultdict(list)
    if not path or not Path(path).is_file():
        return {}
    with open(path, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            toks = tuple(tokens(row["brand"]))
            if toks:
                out[toks[0]].append(BrandHint(row["brand"].strip(), toks, row["category_id"].strip(),
                                              (row.get("confidence") or "medium").strip(),
                                              (row.get("position") or "any").strip() == "first",
                                              (row.get("fallback") or "yes").strip() != "no",
                                              (row.get("pin") or "").strip() == "yes"))
    for v in out.values():
        v.sort(key=lambda h: -len(h.toks))
    return dict(out)


def find_brand(hints: dict[str, list[BrandHint]], toks: list[str]) -> tuple[BrandHint, int] | None:
    """The first hinted brand in toks: (hint, start index)."""
    if not hints:
        return None
    first_content = next((i for i, t in enumerate(toks) if is_content(t)), None)
    for i, t in enumerate(toks):
        for h in hints.get(t, ()):
            if tuple(toks[i:i + len(h.toks)]) == h.toks and (not h.first_only or i == first_content):
                return h, i
    return None


def load_gs1_map(path: Path = GS1_MAP) -> dict[str, tuple[str, str]]:
    out = {}
    with open(path, encoding="utf-8", newline="") as fh:
        for row in csv.DictReader(fh):
            if row["category_id"]:
                out[row["gs1_group"]] = (row["category_id"], row["confidence"] or "medium")
    return out


# --------------------------------------------------------------------------- classify
@dataclass
class Result:
    category_id: str = ""
    confidence: str = ""
    reason: str = ""
    keyword: str = ""
    tied: tuple[str, ...] = ()       # categories tied with the winner (for priors)
    rule_id: str = ""                # what the rules alone said
    brand: str = ""                  # brand hint found in the name (SU11A-52)
    vetoed: frozenset = frozenset()  # nodes vetoed by a hard negative ("!"): refused for GS1 too (SU11A-55)
    pinned: str = ""                 # department pinned by a brand hint (SU11A-55)
    storage: str = ""                # "shelf" / "deli" / "" storage evidence (SU11A-56)


def classify_rules(tax: Taxonomy, name: str, hints: dict[str, list[BrandHint]] | None = None,
                   extra: list[str] | tuple = ()) -> Result:
    """extra: row feature tokens (row_features), appended like the name's own feature tokens."""
    toks = tokens(name)
    if not toks:
        return Result()
    toks += feature_tokens(name) + list(extra)
    res = _classify_name(tax, toks, hints)
    res.storage = storage_of(toks)
    sid = split_storage(res.category_id, res.storage, tax.nodes)
    if sid != res.category_id:
        res = replace(res, category_id=sid, rule_id=sid if res.rule_id == DELI_PICKLES else res.rule_id)
    return res


def _classify_name(tax: Taxonomy, toks: list[str], hints: dict[str, list[BrandHint]] | None) -> Result:
    hit = find_brand(hints, toks) if hints else None
    if not hit:
        return _classify_tokens(tax, toks)
    h, i = hit
    dept = h.category_id.split(".")[0]
    full = _classify_tokens(tax, toks)
    rest = toks[:i] + toks[i + len(h.toks):]
    if full.category_id.split(".")[0] == dept or not any(is_content(t) for t in rest):
        res = full                               # agrees with the brand, or the name is only the brand
    elif h.pin:
        # the department is certain: the best match among its own nodes, first without the
        # brand's words (טבעול is itself a D06.C08 keyword), then with them
        res = _classify_tokens(tax, rest, only=dept)
        if not res.category_id:
            res = _classify_tokens(tax, toks, only=dept)
        if not res.category_id and h.category_id in tax.nodes:
            res = replace(res, category_id=h.category_id, confidence="low" if h.confidence == "low" else "medium",
                          reason="brand", keyword=h.brand, rule_id=h.category_id)
    else:
        res = _classify_tokens(tax, rest)
        if not res.category_id:
            # full matched (if at all) only through the brand's own words
            if h.fallback and h.category_id in tax.nodes:
                conf = "low" if h.confidence == "low" else "medium"
                res = Result(h.category_id, conf, "brand", h.brand, (), h.category_id, vetoed=res.vetoed)
            else:
                res = full
    res.brand = h.brand
    if h.pin and h.category_id in tax.nodes:
        res.pinned = dept
    return res


def _classify_tokens(tax: Taxonomy, toks: list[str], only: str = "") -> Result:
    """only: restrict the candidates to one department (a pinned brand)."""
    eff, head_end = content_index(toks)
    vetoed, hard = set(), set()
    for ri in tax.candidates(toks, negative=True):
        r = tax.negatives[ri]
        if match_rule(r, toks, eff):
            if not r.gs1_only:
                vetoed.add(r.node)
            if r.hard:
                hard.add(r.node)
    best: dict[str, tuple] = {}   # node -> (key, keyword)
    for ri in tax.candidates(toks):
        r = tax.rules[ri]
        if only and r.node.split(".")[0] != only:
            continue
        if any(a in vetoed for a in tax.ancestors(r.node)):
            continue
        m = match_rule(r, toks, eff)
        if not m:
            continue
        start, size = m
        key = (start >= head_end, eff[start], -size, -tax.nodes[r.node].depth)
        if r.node not in best or key < best[r.node][0]:
            best[r.node] = (key, r.text)
    if not best:
        return Result(vetoed=frozenset(hard))
    by_cat: dict[str, tuple] = {}
    for nid, (key, kw) in best.items():
        c = tax.category_of(nid)
        if c not in by_cat or key < by_cat[c][0]:
            by_cat[c] = (key, kw, nid)
    order = sorted(by_cat.items(), key=lambda kv: (kv[1][0], kv[0]))
    win_cat, (wkey, wkw, _) = order[0]
    if "." not in win_cat:
        # A bare department word (חטיף, משקה) won: prefer a category of the same
        # department that matched in the head ("חטיפי טוויקס" -> chocolate).
        inner = [kv for kv in order[1:] if kv[0].startswith(win_cat + ".") and not kv[1][0][0]]
        if inner:
            order = inner + [kv for kv in order if kv not in inner]
            win_cat, (wkey, wkw, _) = order[0]
    # Deepest node of the winning category that matched (sub-type when one did).
    subs = [(k, n, kw) for n, (k, kw) in best.items() if tax.category_of(n) == win_cat]
    deepest = max(tax.nodes[n].depth for _, n, _ in subs)
    k, nid, kw = min((x for x in subs if tax.nodes[x[1]].depth == deepest), key=lambda x: (x[0], x[1]))
    rivals = [(c, v) for c, v in order[1:] if not v[0][0]]   # other categories matched in the head
    tied = tuple(c for c, v in order[1:] if v[0][:3] == wkey[:3])
    if wkey[0]:
        conf = "low"
    elif tied:
        conf = "low"
    elif not rivals:
        conf = "high" if wkey[1] <= 1 else "medium"
    else:
        conf = "medium"
    if tax.nodes[nid].level == "department" and conf == "high":
        conf = "medium"   # a bare generic word (בשר, משקה) names the aisle, not the category
    return Result(nid, conf, "rule", kw, tied, nid, vetoed=frozenset(hard))


def related(a: str, b: str) -> bool:
    return a == b or a.startswith(b + ".") or b.startswith(a + ".")


def combine_gs1(tax: Taxonomy, res: Result, gs1: tuple[str, str] | None) -> Result:
    out = _combine_gs1(tax, res, gs1)
    sid = split_storage(out.category_id, out.storage, tax.nodes)
    return out if sid == out.category_id else replace(out, category_id=sid)


def _combine_gs1(tax: Taxonomy, res: Result, gs1: tuple[str, str] | None) -> Result:
    if not gs1:
        return res
    gid, gconf = gs1
    if gid in tax.nodes and any(a in res.vetoed for a in tax.ancestors(gid)):
        return res      # the name rules the GS1 id out (a hard negative of it matched)
    if res.pinned and gid.split(".")[0] != res.pinned:
        return res      # a pinned brand's department is not open to the GS1 group
    if not res.category_id:
        return replace(res, category_id=gid, confidence="high" if gconf == "high" else "medium", reason="gs1",
                       keyword="", tied=(), rule_id="")
    if related(res.category_id, gid):
        deeper = res.category_id if res.category_id.count(".") >= gid.count(".") else gid
        return replace(res, category_id=deeper, confidence="high", reason="rule+gs1", tied=())
    if gconf == "high":
        return replace(res, category_id=gid, confidence="medium", reason="gs1", tied=())
    return replace(res, confidence="low")


def apply_prior(tax: Taxonomy, res: Result, prior: Counter | None) -> Result:
    """Break a rule tie with the manufacturer's confident categories."""
    if not res.tied or res.reason != "rule" or not prior:
        return res
    total = sum(prior.values())
    if total < 5:
        return res
    pool = (tax.category_of(res.category_id),) + res.tied
    scored = sorted(((prior.get(c, 0), c) for c in pool), reverse=True)
    n, cat = scored[0]
    if n == 0 or n / total < 0.6:
        return res
    nid = res.category_id if tax.category_of(res.category_id) == cat else cat
    conf = "medium" if n / total >= 0.8 and total >= 10 else "low"
    return replace(res, category_id=nid, confidence=conf, reason="prior")


# --------------------------------------------------------------------------- attributes
_UNITS = {
    "גרם": ("g", 1), "גר": ("g", 1), "גר'": ("g", 1), "ג": ("g", 1), "ג'": ("g", 1), "גרמים": ("g", 1),
    "ק\"ג": ("g", 1000), "קג": ("g", 1000), "קילו": ("g", 1000), "קילוגרם": ("g", 1000), "kg": ("g", 1000),
    "g": ("g", 1), "gr": ("g", 1),
    "מ\"ל": ("ml", 1), "מל": ("ml", 1), "מ'ל": ("ml", 1), "מיליליטר": ("ml", 1), "ml": ("ml", 1),
    "ליטר": ("ml", 1000), "ל": ("ml", 1000), "ל'": ("ml", 1000), "ליט'": ("ml", 1000), "ליטרים": ("ml", 1000),
    "l": ("ml", 1000), "lt": ("ml", 1000),
}
_UNIT_ALT = "|".join(sorted((re.escape(u) for u in _UNITS), key=len, reverse=True))
_SIZE = re.compile(rf"(?<![\d.,])(\d+(?:[.,]\d+)?)\s?({_UNIT_ALT})(?=$|[\s\d.,)/*x×+-])")
_MULT = re.compile(r"(?<![\d.])(\d{1,2})\s?[x*×]\s?(\d+(?:[.,]\d+)?)(?![\d])")
_MULT_REV = re.compile(r"(?<![\d.])(\d+(?:[.,]\d+)?)\s?[x*×]\s?(\d{1,2})(?![\d.,])")
_UNITS_N = re.compile(r"(?<![\d.])(\d{1,3})\s?(?:יח'|יח|יחידות|יחי'|pcs)(?=$|[\s.,)])")
_PACK_WORDS = {"זוג": 2, "צמד": 2, "שלישיית": 3, "שלישייה": 3, "שלישית": 3, "שלשיית": 3, "רביעיית": 4,
               "רביעייה": 4, "רביעית": 4, "רבעיית": 4, "חמישיית": 5, "שישיית": 6, "שישייה": 6, "שישית": 6}
_PCT = re.compile(r"(?<![\d.])(\d{1,2}(?:[.,]\d)?)\s?%")
_RX = {
    "organic": re.compile(r"(?<!\S)(אורגני|אורגנית|אורגניים|אורגניות|organic)(?=$|\s)"),
    "gluten_free": re.compile(r"ללא גלוטן|נטול גלוטן|נטולת גלוטן|גלוטן פרי|gluten free"),
    "vegan": re.compile(r"(?<!\S)(טבעוני|טבעונית|טבעוניים|טבעוניות|vegan|ויגן)(?=$|\s)|על בסיס צמחי"),
    "sugar_free": re.compile(r"ללא (תוספת )?סוכר|נטול סוכר|(?<!\S)(דיאט|זירו|zero)(?=$|\s)"),
    "reduced": re.compile(r"(?<!\S)(דל|דלת|מופחת|מופחתת|לייט|light)(?=$|\s)"),
    "lactose_free": re.compile(r"ללא לקטוז|נטול לקטוז|נטולת לקטוז|דל לקטוז"),
    "kosher_passover": re.compile(r"כשר לפסח|(?<!\S)לפסח(?=$|\s)"),
}
_KOSHER = [("בד\"צ", re.compile(r"(?<!\S)(בד\"צ|בדץ|בד\"ץ)(?=$|\s)|העדה החרדית|עדה החרדית|בית יוסף|רובין|לנדא|חתם סופר|שארית|מחזיקי הדת")),
           ("מהדרין", re.compile(r"(?<!\S)(מהדרין|למהדרין)(?=$|\s)")),
           ("חלק", re.compile(r"(?<!\S)חלק(?=$|\s)"))]
_FLAVOUR = re.compile(r"(?<!\S)(?:בטעם|בטעמי) (\S+(?: \S+)?)")
_SCENT = re.compile(r"(?<!\S)(?:בניחוח|ריח) (\S+(?: \S+)?)")
PLACEHOLDER_MFR = re.compile(r"^(|לא ידוע|none|null|unknown|כללי|-+|,|\.|הפריט בפיקוח|0|אין|לא מוגדר|\?+)$")


def _num(s: str) -> float:
    return float(s.replace(",", "."))


def parse_size(name_norm: str) -> tuple[float, str] | None:
    m = _SIZE.search(name_norm)
    if not m:
        return None
    unit, mult = _UNITS[m.group(2)]
    val = _num(m.group(1)) * mult
    # "1 ל" / "1.5 ל" are litres; "ל" after a big number is still litres by rule.
    return (round(val, 3), unit)


def parse_pack(name_norm: str) -> int | None:
    m = _MULT.search(name_norm)
    if m:
        a, b = int(m.group(1)), _num(m.group(2))
        # 6*1.5 -> 6 packs of 1.5; 33*33 (a size like 33x33 ס"מ) is not a pack.
        if 2 <= a <= 48 and not (a == b and a > 12):
            return a
    m = _MULT_REV.search(name_norm)
    if m and 2 <= int(m.group(2)) <= 24 and "." in m.group(1):
        return int(m.group(2))
    m = _UNITS_N.search(name_norm)
    if m and 2 <= int(m.group(1)) <= 500:
        return int(m.group(1))
    for t in name_norm.split(" "):
        if t in _PACK_WORDS:
            return _PACK_WORDS[t]
    return None


def extract_attributes(tax: Taxonomy | None, node_id: str, name: str, row: dict | None = None,
                       brand_hint: str = "") -> dict:
    """Attributes for one item, filtered to those its node offers (all when unclassified).

    brand: GS1 brand, else a real manufacturer, else the brand hint found in the name.
    """
    row = row or {}
    n = normalize(name)
    allowed = set(tax.attrs_for(node_id)) if (tax and node_id) else None
    out: dict = {}
    brand = (row.get("gs1_brand") or "").strip()
    if not brand:
        m = normalize(row.get("manufacturer") or "").strip(" .,-'\"")
        brand = "" if PLACEHOLDER_MFR.match(m) else (row.get("manufacturer") or "").strip()
    brand = brand or brand_hint
    if brand:
        out["brand"] = brand
    size = parse_size(n)
    if size:
        out["size_value"], out["size_unit"] = size
    pack = parse_pack(n)
    if pack:
        out["pack_count"] = pack
    pct = _PCT.findall(n)
    if pct:
        v = _num(pct[0])
        if allowed is not None and "alcohol_pct" in allowed:
            out["alcohol_pct"] = v
        elif allowed is not None and "cocoa_pct" in allowed and re.search(r"קקאו|מריר", n):
            out["cocoa_pct"] = v
        elif allowed is not None and "fat_pct" in allowed and v <= 45:
            out["fat_pct"] = v
    for key, rx in _RX.items():
        if rx.search(n):
            out[key] = True
    diet = row.get("gs1_diet") or ""
    if "ללא גלוטן" in diet:
        out["gluten_free"] = True
    if "טבעוני" in diet or "ויגן" in diet:
        out["vegan"] = True
    if "ללא לקטוז" in diet:
        out["lactose_free"] = True
    if "ללא סוכר" in diet or "ללא תוספת סוכר" in diet:
        out["sugar_free"] = True
    for level, rx in _KOSHER:
        if rx.search(n):
            if level == "חלק" and not (node_id.startswith("D03") or node_id.startswith("D04")):
                continue
            out["kosher_level"] = level
            break
    kos = row.get("gs1_kosher") or ""
    if kos:
        for t in ("פרווה", "חלבי", "בשרי"):
            if t in kos:
                out["kosher_type"] = t
                break
        if "kosher_level" not in out:
            if "בדצ" in kos or "בד\"צ" in kos or "העדה החרדית" in kos:
                out["kosher_level"] = "בד\"צ"
            elif "מהדרין" in kos:
                out["kosher_level"] = "מהדרין"
            elif "הרבנות" in kos or "רבנות" in kos:
                out["kosher_level"] = "רבנות"
    m = _FLAVOUR.search(n)
    if m:
        out["flavour"] = m.group(1)
    m = _SCENT.search(n)
    if m:
        out["scent"] = m.group(1)
    if re.search(r"(?<!\S)(טרי|טרייה|טריים|טריות)(?=$|\s)", n):
        out["state"] = "fresh"
    elif re.search(r"(?<!\S)(קפוא|קפואה|קפואים|קפואות|מוקפא|מוקפאת|מוקפאים)(?=$|\s)", n):
        out["state"] = "frozen"
    elif re.search(r"(?<!\S)(מעושן|מעושנת|מעושנים)(?=$|\s)", n):
        out["state"] = "smoked"
    if str(row.get("is_weighted") or "") == "1" or re.search(r"(?<!\S)(במשקל|לק\"ג)(?=$|\s)", n):
        out["weighted"] = True
    if allowed is not None:
        out = {k: v for k, v in out.items() if k in allowed}
    return out


# --------------------------------------------------------------------------- run
def leading_token(name: str) -> str:
    for t in tokens(name):
        if is_content(t):
            return t
    return ""


def item_name(r: dict) -> str:
    """The name to classify: items.item_name, else search_items.name_norm, else the
    item_chain_names fallback (SU11A-52 export column icn_name)."""
    return r.get("name") or r.get("name_norm") or r.get("icn_name") or ""


def classify_all(tax: Taxonomy, rows: list[dict], gmap: dict | None,
                 hints: dict[str, list[BrandHint]] | None = None) -> list[Result]:
    first = []
    for r in rows:
        res = classify_rules(tax, item_name(r), hints, row_features(r.get("item_code", ""), r.get("is_weighted")))
        g = gmap.get(r.get("gs1_group") or "") if gmap else None
        first.append(combine_gs1(tax, res, g))
    prior: dict[str, Counter] = defaultdict(Counter)
    for r, res in zip(rows, first):
        m = normalize(r.get("manufacturer") or "").strip(" .,-'\"")
        if res.category_id and res.confidence in ("high", "medium") and not PLACEHOLDER_MFR.match(m):
            prior[m][tax.category_of(res.category_id)] += 1
    out = []
    for r, res in zip(rows, first):
        m = normalize(r.get("manufacturer") or "").strip(" .,-'\"")
        out.append(apply_prior(tax, res, prior.get(m)))
    return out


def _w(r: dict) -> int:
    try:
        return max(1, int(r.get("chains_live") or 1))
    except ValueError:
        return 1


def evaluate(tax: Taxonomy, rows: list[dict], final: list[Result], rule_only: list[Result], gmap: dict) -> dict:
    rep: dict = {"items": len(rows)}
    for label, res in (("final", final), ("rules_only", rule_only)):
        cnt, wcnt = Counter(), Counter()
        for r, x in zip(rows, res):
            c = x.confidence or "unclassified"
            cnt[c] += 1
            wcnt[c] += _w(r)
        tot, wtot = sum(cnt.values()), sum(wcnt.values())
        rep[f"coverage_{label}"] = {k: {"items": cnt[k], "pct": round(100 * cnt[k] / tot, 1),
                                        "weighted_pct": round(100 * wcnt[k] / wtot, 1)}
                                    for k in ("high", "medium", "low", "unclassified")}
        rep[f"reasons_{label}"] = dict(Counter(x.reason or "none" for x in res))
        buckets = defaultdict(Counter)
        for r, x in zip(rows, res):
            b = "1" if _w(r) <= 1 else "2-4" if _w(r) <= 4 else "5+"
            buckets[b][x.confidence or "unclassified"] += 1
        rep[f"coverage_by_chains_{label}"] = {b: {k: round(100 * v / sum(c.values()), 1) for k, v in c.items()}
                                              for b, c in sorted(buckets.items())}
    # (a) agreement with the GS1 group map, rules alone
    agree = Counter()
    by_conf = defaultdict(Counter)
    by_dept = defaultdict(Counter)
    confusion = Counter()
    for r, x in zip(rows, rule_only):
        g = gmap.get(r.get("gs1_group") or "")
        if not g:
            continue
        gid, gconf = g
        agree["mapped"] += 1
        if not x.category_id:
            agree["no_rule"] += 1
            continue
        agree["predicted"] += 1
        level = gid.count(".")   # 0 department, 1+ category
        pred = x.category_id.split(".")[0] if level == 0 else tax.category_of(x.category_id)
        want = gid if level == 0 else tax.category_of(gid)
        ok = pred == want
        dept_ok = x.category_id.split(".")[0] == gid.split(".")[0]
        agree["correct"] += ok
        agree["dept_correct"] += dept_ok
        by_conf[gconf]["n"] += 1
        by_conf[gconf]["ok"] += ok
        by_conf[x.confidence]["rule_n"] += 1
        by_conf[x.confidence]["rule_ok"] += ok
        by_dept[gid.split(".")[0]]["n"] += 1
        by_dept[gid.split(".")[0]]["ok"] += ok
        if not ok:
            confusion[(want, pred)] += 1
    n = agree["predicted"] or 1
    rep["gs1_agreement"] = {
        "mapped_items": agree["mapped"], "rule_predicted": agree["predicted"],
        "rule_coverage_pct": round(100 * agree["predicted"] / (agree["mapped"] or 1), 1),
        "accuracy_pct": round(100 * agree["correct"] / n, 1),
        "department_accuracy_pct": round(100 * agree["dept_correct"] / n, 1),
        "by_map_confidence": {k: round(100 * v["ok"] / v["n"], 1) for k, v in by_conf.items() if v["n"]},
        "by_rule_confidence": {k: {"n": v["rule_n"], "acc": round(100 * v["rule_ok"] / v["rule_n"], 1)}
                               for k, v in by_conf.items() if v["rule_n"]},
        "by_department": {k: {"n": v["n"], "acc": round(100 * v["ok"] / v["n"], 1)} for k, v in sorted(by_dept.items())},
        "top_confusions": [{"gs1": a, "rule": b, "n": c, "gs1_he": tax.path_he(a) if a in tax.nodes else a,
                            "rule_he": tax.path_he(b) if b in tax.nodes else b}
                           for (a, b), c in confusion.most_common(20)],
    }
    lead = Counter(leading_token(item_name(r)) for r, x in zip(rows, final) if not x.category_id)
    rep["unclassified_leading_top50"] = lead.most_common(50)
    dept = Counter()
    for r, x in zip(rows, final):
        dept[x.category_id.split(".")[0] if x.category_id else "-"] += 1
    rep["items_by_department"] = {k: {"items": v, "name_he": tax.nodes[k].name_he if k in tax.nodes else "unclassified"}
                                  for k, v in sorted(dept.items())}
    return rep


def _md5(s: str) -> str:
    return hashlib.md5(s.encode("utf-8")).hexdigest()


def review_sample(tax: Taxonomy, rows: list[dict], res: list[Result], n_total: int = 400, n_top: int = 100) -> list[dict]:
    """100 items with the highest chains_live, then a stratified draw by department x confidence."""
    idx = sorted(range(len(rows)), key=lambda i: (-_w(rows[i]), _md5(rows[i]["item_code"])))
    chosen, seen = [], set()
    for i in idx[:n_top]:
        chosen.append((i, "top_chains"))
        seen.add(i)
    strata = defaultdict(list)
    for i in range(len(rows)):
        if i in seen:
            continue
        d = res[i].category_id.split(".")[0] if res[i].category_id else "-"
        strata[(d, res[i].confidence or "unclassified")].append(i)
    for k in strata:
        strata[k].sort(key=lambda i: _md5(rows[i]["item_code"]))
    keys = sorted(strata)
    left = n_total - len(chosen)
    # Round-robin over strata so every department x confidence cell is seen.
    pos = 0
    while left > 0 and any(strata[k] for k in keys):
        k = keys[pos % len(keys)]
        if strata[k]:
            chosen.append((strata[k].pop(0), f"{k[0]}/{k[1]}"))
            left -= 1
        pos += 1
    out = []
    for i, stratum in chosen:
        r, x = rows[i], res[i]
        out.append({
            "item_code": r["item_code"], "name": r["name"], "manufacturer": r.get("manufacturer") or "",
            "gs1_brand": r.get("gs1_brand") or "", "gs1_group": r.get("gs1_group") or "",
            "chains_live": r.get("chains_live") or "", "stratum": stratum,
            "predicted_category_id": x.category_id,
            "predicted_path_he": tax.path_he(x.category_id) if x.category_id else "",
            "confidence": x.confidence or "unclassified", "reason": x.reason, "matched_keyword": x.keyword,
            "correct_category_id": "",
        })
    return out


def read_export(path: Path) -> list[dict]:
    opener = gzip.open if str(path).endswith(".gz") else open
    with opener(path, "rt", encoding="utf-8", newline="") as fh:
        return list(csv.DictReader(fh))


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--input", required=True, type=Path)
    ap.add_argument("--out-dir", required=True, type=Path)
    ap.add_argument("--taxonomy", type=Path, default=TAXONOMY)
    ap.add_argument("--gs1-map", type=Path, default=GS1_MAP)
    ap.add_argument("--brand-hints", default=str(BRAND_HINTS), help='brand hints CSV; "" = none')
    ap.add_argument("--review-sample", type=Path)
    ap.add_argument("--no-gs1", action="store_true", help="rules and priors only")
    a = ap.parse_args(argv)
    tax = load_taxonomy(a.taxonomy)
    gmap = load_gs1_map(a.gs1_map)
    hints = load_brand_hints(Path(a.brand_hints)) if a.brand_hints else {}
    rows = read_export(a.input)
    rule_only = classify_all(tax, rows, None, hints)
    final = rule_only if a.no_gs1 else classify_all(tax, rows, gmap, hints)
    a.out_dir.mkdir(parents=True, exist_ok=True)
    with gzip.open(a.out_dir / "predictions.csv.gz", "wt", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh)
        w.writerow(["item_code", "name", "category_id", "path_he", "confidence", "reason", "keyword",
                    "rule_category_id", "chains_live", "gs1_group", "brand_hint", "attributes", "pinned",
                    "storage"])
        for r, x in zip(rows, final):
            attrs = extract_attributes(tax, x.category_id, item_name(r), r, x.brand)
            w.writerow([r["item_code"], item_name(r), x.category_id, tax.path_he(x.category_id) if x.category_id else "",
                        x.confidence, x.reason, x.keyword, x.rule_id, r.get("chains_live", ""),
                        r.get("gs1_group", ""), x.brand, json.dumps(attrs, ensure_ascii=False), x.pinned,
                        x.storage])
    rep = evaluate(tax, rows, final, rule_only, gmap)
    (a.out_dir / "report.json").write_text(json.dumps(rep, ensure_ascii=False, indent=1), encoding="utf-8")
    with open(a.out_dir / "unclassified_leading.tsv", "w", encoding="utf-8") as fh:
        for t, c in rep["unclassified_leading_top50"]:
            fh.write(f"{t}\t{c}\n")
    if a.review_sample:
        sample = review_sample(tax, rows, final)
        with open(a.review_sample, "w", encoding="utf-8", newline="") as fh:
            w = csv.DictWriter(fh, list(sample[0]), lineterminator="\n")
            w.writeheader()
            w.writerows(sample)
    print(json.dumps({k: rep[k] for k in ("items", "coverage_final", "coverage_rules_only", "gs1_agreement")},
                     ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
