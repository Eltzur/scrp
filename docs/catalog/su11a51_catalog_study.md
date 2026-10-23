# SU11A-51 — catalogue categorisation: data study, taxonomy v0, rule classifier prototype

Date: 23 Oct 2026. Offline work. Production was only read: one read-only export over ssh (READ ONLY transaction, `statement_timeout` 60 s, `ulimit -v 1500000`, server-side cursor, 21 s). No schema, data, API, web or mobile change.

## Files

| Path | What |
|---|---|
| `docs/catalog/taxonomy_v0.csv` | 16 departments, 151 categories, 34 sub-types, with keyword rules, negatives and attributes. **For Dude's review.** |
| `docs/catalog/attributes_v0.csv` | 20 filter attributes (key, Hebrew name, type, unit, parse hints, applies_to) |
| `docs/catalog/gs1_group_map_v0.csv` | All 418 GS1 groups seen on live items → our id. 314 are mapped (13,613 items); the rest are blank, with a reason. |
| `docs/catalog/review_sample_v0.csv` | 400 items for Dude to grade. Fill `correct_category_id` only where the prediction is wrong. |
| `docs/catalog/leading_words_top300_v0.csv` | The top 300 leading 1–2 word combinations, with counts and 3 example names each |
| `scripts/catalog/classify_rules.py` | Offline classifier, evaluation and review-sample writer (no database) |
| `tests/test_classify_rules.py` | 53 tests |

The raw export (124,974 rows, 3.7 MB gzip) is **not** in the repo. It stays in a local scratch folder. To reproduce:

    python -m scripts.catalog.classify_rules --input EXPORT.csv.gz --out-dir OUT [--review-sample docs/catalog/review_sample_v0.csv] [--no-gs1]

Background:
- **The SU11A-35 audit (`scripts/audit_catalog.py`) was never run on the server.** This study replaces it as the data basis.
- **The SU11A-6/7 draft** (`docs/super/category_taxonomy.md`, 20 top-level categories) was folded in. Its overlap decisions are kept, with one exception: frozen fruit now sits in the freezer department.

---

## 1. Data study (production, 23 Oct 2026; search_items built 11:48)

### Population
- `search_items` has 125,589 rows. **124,974 are live and not pseudo** (615 are coupon or ₪0.01 rows); this is the study's base.
- By `chains_live`:

  | Chains | Items | Share |
  |---|---:|---:|
  | 1 | 82,687 | 66.2% |
  | 2–4 | 25,550 | 20.4% |
  | 5+ | 16,737 | 13.4% |

- 398 items are promo-only.
- **1,355 live items have an empty name** in both `items.item_name` and `search_items.name_norm`. 1,353 of them are sold by one chain. Search can never find them. This is a data-quality issue to raise separately.
- 77 items are service rows: פיקדון / פקדון 44, משלוח 32, דמי 1. Like coupons, they should be hidden (D1-style).
- `items` has 171,240 rows in all.

### GS1 coverage

`gs1.products` holds 30,773 rows:
- 19,577 active;
- 19,550 distinct active GTINs;
- 17,355 with detail (`full_content`).

There are 17,331 image files on disk.

On live items:

| | Items | Share of live |
|---|---:|---:|
| Any GS1 record (active, GTIN = item_code) | 15,366 | 12.3% |
| … with `group_name` | 15,366 | 12.3% |
| … with detail (`full_content`) | 15,312 | 12.3% |

- **By chains:** GS1 covers 2.9% of 1-chain items, 13.7% of 2–4-chain items and 56.4% of 5+-chain items. Weighted by `chains_live`, that is 33.9%.
- **Groups:** 418 distinct `group_name` values. The top 40 are in `gs1_group_map_v0.csv`, sorted by live items. The first ten are:
  - Chocolate 744;
  - Cleaning Accessories 390;
  - Body soap 333;
  - Shampoo 291;
  - Biscuits 286;
  - Laundry detergents 283;
  - Flavoured drinks 280;
  - Cheese (perishable) 241;
  - Canned fish 239;
  - Dry pasta 237.

**Field fill.** Every key is present in every detail record, but it is usually blank (`{"code":"","value":""}`), so these counts are of non-empty values:

| Field (GS1 path) | Live items | Of all live | Of items with detail |
|---|---:|---:|---:|
| Brand (`brandname`) | 15,366 | 12.3% | 100% |
| Net content (`Main_Fields.Net_Content`) | 15,247 | 12.2% | 99.6% |
| Country of origin | 15,312 | 12.3% | 100% |
| GPC code | 15,312 | 12.3% | 100% |
| **Ingredients** (`Ingredient_Sequence_and_Name`) | 14,276 | 11.4% | 93.2% |
| **Nutrition panel** (≥1 filled row) | 9,192 | 7.4% | 60.0% |
| **Allergens** (contains / may contain) | 7,984 | 6.4% | 52.1% |
| **Kashrut** (type / board / rabbinate) | 15,294 | 12.2% | 99.9% |
| Diet information | 3,774 | 3.0% | 24.6% |
| Fat % field | 322 | 0.3% | 2.1% |
| Alcohol % field | 474 | 0.4% | 3.1% |
| Product_Categories_Classification | 14 | 0.0% | 0.1% |
| Internal_Classification | 227 | 0.2% | 1.5% |
| Search words | 11,544 | 9.2% | 75.4% |
| Image file on disk | 15,560 | 12.5% | 100% |

**Common values:**
- **Diet:**
  - ללא גלוטן 1,416;
  - ללא חומרים משמרים 1,208;
  - טבעוני 1,115;
  - ללא צבעי מאכל 742;
  - ויגן פרנדלי 374;
  - ללא תוספת סוכר 307.
- **Kashrut:**
  - פרווה 8,009;
  - לא רלוונטי 4,473;
  - הרבנות הראשית 3,084;
  - בד"צ העדה החרדית 2,340;
  - חלבי 2,197;
  - בד"צ בית יוסף 1,379.
- **GS1's own category fields** (Product_Categories_Classification, Internal_Classification) are practically empty, so they cannot replace `group_name`.

### Name structure (normalised with `db/search_norm.normalize`)
- There are 8,487 distinct first words and 43,765 distinct first two-word combinations.
- First words needed to cover the catalogue:

  | Coverage | 50% | 80% | 90% | 95% |
  |---|---:|---:|---:|---:|
  | First words | 216 | 1,040 | 2,173 | 3,677 |
  | First two words | 3,945 | 19,042 | 31,404 | 37,585 |

  The head is short but the tail is long, so keywords must match anywhere in the name, not only the first word.
- **Top leading words:**
  - סט 1,958;
  - מארז 1,835;
  - יין 1,826;
  - פילה 1,498;
  - עוגיות 1,227;
  - חטיף 1,067;
  - רוטב 917;
  - גבינת 889;
  - סוכריות 867;
  - גבינה 811;
  - משקה 801;
  - צלחת 793;
  - בקבוק 691;
  - שמן 617;
  - שוקולד 609.

  The full top 300, with examples, is in `leading_words_top300_v0.csv`.
- **Pack words lead many names** (מארז, סט, זוג, שלישיית, מאגדת), so the classifier skips them.
- **General merchandise is large:** plates, candles, clothing, toys and electronics, mostly from single chains.

### Manufacturer
- There are 3,774 distinct cleaned values.
- **85.1% of live items carry a placeholder:**

  | Value | Items |
  |---|---:|
  | לא ידוע | 60,878 |
  | empty | 44,679 |
  | כללי | 566 |
  | unknown | 198 |
  | הפריט בפיקוח | 7 |

  The "None", "---" and "," forms from the brief do not occur after cleaning.
- **Top real values** include משתנה 342, מרלוג gsd 261, רמי לוי 170, אסם השקעות 162, ביכורי השקמה 149, קרלברג 146, שטראוס גרופ 143 and תנובה 136.
- The same firm is spelled several ways (תנובה / תנובה בע"מ, סנו מפעלי ברונוס בע / בעמ).
- **Effect on the classifier:** manufacturer priors almost never fire. They broke 2 ties in the whole catalogue. Brand facets will have to come from GS1 brand or a name-based brand lexicon.

### Attribute parsing on names (regex on the normalised name; share of all 124,974)

| Attribute | Match rate | Main values | False positives seen |
|---|---:|---|---|
| fat % (`N%`) | 2.0% | 5% 337, 3% 137, 28% 105 | 372 of the hits are not fat: cocoa %, alcohol %, "0% אלומיניום", vinegar 6%. Only use it where the category offers fat_pct. |
| size (number + unit) | 28.7% | 500 גרם 1,252, 750 מ"ל 1,100, 1 ליטר 864 | "ל" after a number is almost always litres (444 checked). |
| pack (N*M, מארז, זוג, N יח') | 9.0% | מארז 2,512, זוג 987, מגש 778 | "33*33" and "50x85" are sizes in cm (now rejected). "זוג" in clothing means a pair. |
| kashrut markers | 1.6% | חלק 1,269, מהדרין 269, בד"צ 110 | "חלק" means glatt only in meat names; elsewhere it means "smooth". |
| gluten-free | 0.3% | ללא גלוטן 426 | none seen |
| vegan | 0.3% | טבעוני 215, צמחי 148 | Bare "צמחי" is mostly "שמן צמחי" (82). Dropped. |
| sugar-free | 0.6% | ללא סוכר 321, זירו 171 | "דיאט" inside "רדיאטור" (fixed by matching whole words) |
| reduced (דל / מופחת / לייט) | 0.5% | קל 244, לייט 145 | "קל" means "light" only rarely (משקה קל, פתח קל). Dropped. |
| organic | 1.3% | אורגני 1,572, ביו 113 | "ביו" matches inside names (סיביו). Dropped. |
| lactose-free | 0.02% | נטול לקטוז 17 | none |

**Fill rates after classification** (attributes kept only where the item's category offers them):

| Attribute | Fill |
|---|---|
| size | 28.8% |
| brand | 22.8% |
| sold by weight | 10.3% |
| kosher type (GS1 only) | 8.4% |
| kosher level | 7.5% |
| pack count | 6.8% |
| fat % | 28% of dairy |
| alcohol % | 3% of D10 (wine names rarely state it) |
| cocoa % | 7% of chocolate |

Structured fields are poor too. `items.unit_of_measure` has 4,650 + 1,236 + 449 values that are mojibake ("???¨??"), plus "Unknown" or "לא ידוע" on 4,722 items. Sizes therefore have to come from names or GS1.

---

## 2. Taxonomy v0 — design choices

**Shopper aisles, from our data.**
- Departments and categories come from the leading-word list and the GS1 group counts above, not from a retailer's tree.
- SU11A-6/7 overlap decisions are kept:
  - crackers and cookies are snacks;
  - frozen bakery is frozen;
  - ice-cream bars are ice cream;
  - baby toiletries are baby;
  - toilet blocks are cleaning;
  - pickles are deli;
  - cooking sauces and table condiments are split.
- **One change:** frozen fruit moves to the freezer department (D06.C02).

**One primary category per item. Traits are attributes, not categories:** kosher, organic, gluten-free, vegan, sugar-free, reduced, fat %, size, pack count, flavour, state, sold by weight, scent, alcohol % and cocoa %. Attributes are listed per node and inherited downward:
- every department offers brand / size / pack;
- D01–D10 add the food set;
- dairy adds fat % and lactose-free;
- alcohol adds alcohol %;
- chocolate adds cocoa %;
- meat adds state and sold by weight.

**16 departments, one more than the brief's ~15.** General merchandise is 17% of live items: 14,731 home + 6,673 clothing / leisure. One department would mix pots with toys, so it is split into D15 בית ומטבח and D16 ביגוד, פנאי ומסיבות. Merging D16 into D15 gives 15.

| ID | Department | Categories | Sub-types | Live items (final) |
|---|---|---:|---:|---:|
| D01 | פירות וירקות | 5 | 0 | 7,424 |
| D02 | מוצרי חלב, ביצים ותחליפים | 7 | 6 (milk 3, cheese 3) | 5,711 |
| D03 | בשר, עוף ודגים | 9 | 0 | 9,866 |
| D04 | מעדנייה, נקניקים וסלטים | 6 | 3 (cold cuts) | 4,749 |
| D05 | לחם ומאפים | 7 | 0 | 3,491 |
| D06 | קפואים | 8 | 0 | 3,086 |
| D07 | מזווה ובישול | 23 | 0 | 13,966 |
| D08 | חטיפים וממתקים | 10 | 6 (chocolate 3, salty snacks 3) | 12,317 |
| D09 | משקאות | 10 | 6 (soft drinks 2, coffee 4) | 4,931 |
| D10 | אלכוהול וטבק | 5 | 8 (wine 3, spirits 5) | 4,807 |
| D11 | ניקיון, נייר וחד פעמי | 12 | 5 (laundry 3, dishwashing 2) | 8,365 |
| D12 | טיפוח, היגיינה ובריאות | 18 | 0 | 9,727 |
| D13 | תינוקות | 7 | 0 | 1,153 |
| D14 | חיות מחמד | 3 | 0 | 826 |
| D15 | בית ומטבח | 14 | 0 | 14,731 |
| D16 | ביגוד, פנאי ומסיבות | 7 | 0 | 6,673 |
| | **Total** | **151** | **34** | 111,823 classified, 13,151 not |

**Sub-types only where the data supports a filter shoppers use:**
- milk;
- cheese;
- cold cuts;
- chocolate;
- salty snacks;
- soft drinks;
- coffee;
- wine;
- spirits;
- laundry;
- dishwashing.

Yogurt and spices stay flat for now, because their names rarely carry the distinguishing word.

**Keyword grammar** (in the CSV, one keyword per `|` item, matched on normalised whole words):

| Form | Meaning |
|---|---|
| `a b` | consecutive words |
| `a*` | word prefix; Hebrew final letters are unified, so `מעושן*` matches מעושנת |
| `x,y+z` | conjunction: one of the comma alternatives of every `+` part, anywhere in the name (`צלחות,כוסות+חד פעמי*,פלסטיק`) |

Department rows can carry keywords for bare aisle words: בשר, משקה, חטיף, תערובת, כלי. A department-level result is capped at medium.

**IDs are stable (D01.C03.S02)** and never reused. A later version may add ids or retire them with a note, but must not renumber.

**Review points for Dude:**
1. 16 vs 15 departments.
2. Frozen fruit in D06.
3. Hummus / tahini as a deli category (D04.C02), while dry chickpeas are pantry.
4. Tobacco inside D10.
5. Seafood (D03.C09) kept because chains sell it.
6. Liqueurs split out of spirits.
7. Cereal bars in snacks, granola in breakfast cereals.

---

## 3. Classifier prototype — results

### Rules
- **Precedence:**
  1. a match before a connector word (עם, בטעם, ללא, של …) beats one after it;
  2. then the earliest content word (pack words, numbers and units are not counted);
  3. then the longer keyword;
  4. then the deeper node.

  Inside the winning category, the deepest matching sub-type is reported.
- **Negatives:** a negative of a node or of any ancestor vetoes that node.
- **Confidence:**

  | Level | When |
  |---|---|
  | high | the winning match is in the first two content words and no other category matched before a connector |
  | medium | it won on position or length, or matched later |
  | low | a tie between categories, or a match only after a connector |

- **GS1 map:**
  - a group that agrees with the rule (same lineage) → the deeper id, high;
  - no rule match → the GS1 id;
  - a disagreement with a "high" map row → the GS1 id at medium;
  - a disagreement with a "medium" map row → the rule, lowered to low.
- **Manufacturer priors:** tie-break only.

### (b) Coverage on the 124,974 live items

| Confidence | Final (rules + GS1) | Weighted by chains_live | Rules only |
|---|---:|---:|---:|
| high | 80,823 (64.7%) | 65.0% | 78,820 (63.1%) |
| medium | 28,801 (23.0%) | 24.6% | 30,802 (24.6%) |
| low | 2,199 (1.8%) | 3.4% | 1,234 (1.0%) |
| unclassified | 13,151 (10.5%) | 7.0% | 14,118 (11.3%) |

- 1,355 of the unclassified items have no name. Without them, 9.5% is unclassified.
- **By chains, final:**

  | Chains | high | medium | low | unclassified |
  |---|---:|---:|---:|---:|
  | 1 | 64.6% | 21.8% | 0.9% | 12.6% |
  | 2–4 | 64.7% | 25.1% | 2.2% | 8.1% |
  | 5+ | 64.8% | 26.2% | 5.2% | 3.8% |

- **Reasons:**

  | Reason | Items |
  |---|---:|
  | rule | 99,432 |
  | rule+gs1 | 8,874 |
  | gs1 | 3,515 |
  | prior | 2 |

### (a) Agreement with the GS1 group map (rules alone, GS1 not used)
- 13,613 items have a mapped GS1 group. The rules classified 12,646 of them (92.9%).
- **Accuracy at the mapped level: 70.1% by category, 80.4% by department.**
  - By map confidence: 71.9% on "high" map rows, 65.7% on "medium" ones.
  - By rule confidence: high 77.2% (7,558 items), medium 61.1% (4,829), low 30.9% (259).
- By department:

  | Dept | D01 | D02 | D03 | D04 | D05 | D06 | D07 | D08 | D09 | D10 | D11 | D12 | D13 | D14 | D15 |
  |---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|---|
  | Accuracy | 37% | 74% | 77% | 63% | 44% | 41% | 75% | 57% | 75% | 90% | 79% | 81% | 81% | 67% | 17% |

  D01 and D15 rest on very few mapped items. D06 is low because frozen goods rarely say "קפוא", which GS1 knows.
- **GS1 is a noisy yardstick.** Two hand audits each checked a random set of disagreements (40, then a fresh 30). About half were rule errors (20 of 40, then 17 of 30). The rest were:
  - GS1 filing errors: "Cleaning Accessories" holds liquid cleaners; cookies are filed as "Bread"; Mentos as gum;
  - deliberate taxonomy differences: chocolate-coated wafers under wafers; baby shampoo under baby.

  **The estimated true category accuracy on GS1 items is about 82%.**

### Hand audit of items without GS1 (the 88% GS1 cannot check)
Run on a fresh random sample after the last rule change:
- high: 35 of 40 correct (≈ 88%);
- medium: 22 of 30 (≈ 73%);
- low: 6 of 10.

This is one person's judgement on small samples, so treat it as ±10 points. The review sample below is the real measure.

### (c) Gaps: top unclassified leading words (final)

These are the words to add next:
- ספריי 47;
- קוקוס 44;
- מיקס 43;
- אובלי 38;
- עגבניות 37 (vetoed by a negative);
- ערכת 37;
- צנצנת 35;
- גל 33;
- אבקת 32;
- עוגת 30;
- לה 29;
- סוכ 29 (a truncated name);
- מעיין 29;
- עצמות 28;
- פיקדון 28 (service row);
- פלפל 28;
- עוגה 28;
- מלא 28;
- גריל 27;
- עגלת 26;
- מקלות 26;
- מברשת 26;
- קבוקים 25;
- ראש 25;
- פת 25;
- בקבוק 25;
- בונדוק 24;
- סל 24;
- משלוח 24 (service row);
- כתף 24;
- מג 24;
- פרוסות 24;
- בייבי 23;
- בלדי 22;
- בונ 22;
- קוקטייל 22;
- גביעי 22;
- כ.ברכה 22;
- קשת 21;
- סירופ 21;
- מסנן 21;
- תרסיס 21;
- כיסוי 21;
- קליפסים 21;
- טופר 21;
- סיכות 21;
- מתנה 21;
- כאמל 20;
- סברס 20.

The tail is truncated or brand-only names (סוכ, בונ, מג, לה). Rules alone will not get much past 90%.

**Known rule weaknesses** (seen in the audits):
- brand-only names (שמיר = a hummus brand, read as dill);
- frozen goods without a frozen word;
- generic "חטיף X" names land at department level;
- "פילה" is fish by default (beef fillets need בקר in the name);
- general-merchandise words (מעמד, משטח, כלי) are coarse.

### Review sample (`review_sample_v0.csv`)
400 rows:
- **the 100 items with the most chains** (sorted by `chains_live`, then `md5(item_code)`);
- **a round-robin draw over department × confidence**, which yields 18–21 items per department and 7 unclassified.

| Confidence | Rows |
|---|---:|
| high | 179 |
| medium | 114 |
| low | 98 |
| unclassified | 9 |

Columns:
- item_code, name, manufacturer, gs1_brand, gs1_group, chains_live, stratum;
- the prediction: predicted_category_id, predicted_path_he, confidence, reason, matched_keyword;
- **empty `correct_category_id` for Dude.** Leave it blank when the prediction is right. When it is wrong, write any id from `taxonomy_v0.csv`, at category or sub-type level.

---

## 4. Next session — the AI-assisted pass

**Scope.** The input per item is name + manufacturer (when not a placeholder) + GS1 group. The output is one id from `taxonomy_v0.csv`, plus a confidence.

| Option | Items | Average input text |
|---|---:|---|
| A. unclassified + low (named) | 13,995 | 30.5 characters |
| **B. A + medium (recommended)** | **42,796** | 33.5 characters |
| C. every named live item (second opinion on all) | 123,619 | 32.9 characters |

The recommended set B covers everything the rules are unsure of. High-confidence rule results (≈ 88% right) are only spot-checked.

**Cost basis** (token counts; prices to be applied at run time):
- **Prompt:**
  - the category list (185 ids + Hebrew names) is about 4–5K tokens, cacheable;
  - the instructions are about 1K;
  - SU11A-7's overlap rules go in as text.
- **Per item:** about 20–25 input tokens for Hebrew text at about 30–34 characters, and about 8–12 output tokens (id + confidence).
- **For set B:** in batches of 50 items, that is about 860 requests, and in total about:
  - 0.9–1.1M uncached item tokens;
  - about 5M cached prompt tokens;
  - 0.35–0.5M output tokens.
- Batch processing (asynchronous, discounted) fits: nothing is latency-bound.

**Evaluation:**
- grade on Dude's corrected `review_sample_v0.csv` and on the GS1-mapped items;
- report agreement with the rules by confidence;
- accept the AI label where the rules are unclassified, low or medium, and send rule-vs-AI conflicts on high items to review.

**Storage (when approved):**
- the SU11A-35 proposal still fits:
  - `categories` (this CSV);
  - `item_categories` (item_code, category_id, source rule / gs1 / ai / manual, confidence, version);
  - `item_attributes`;
- facet counts are read from `search_items`, never from prices.

That needs a migration, so it is a separate approved session.

## 5. GS1 fields for task #2 (nutrition, ingredients, kashrut)

| | Ingredients | Nutrition | Allergens | Kashrut block | Image |
|---|---:|---:|---:|---:|---:|
| All live items | 11.4% | 7.4% | 6.4% | 12.2% | 12.5% |
| 1-chain items | 2.6% | 1.5% | 1.4% | 2.9% | 3.0% |
| 2–4 chains | 12.4% | 7.2% | 6.7% | 13.7% | 14.0% |
| 5+ chains | 53.5% | 36.3% | 30.7% | 56.3% | 56.9% |
| Weighted by chains_live | 32.1% | 21.8% | — | — | — |

- Where GS1 detail exists, ingredients (93%) and kashrut (99.9%) are almost always filled. Nutrition (60%) and allergens (52%) are not.
- Most of what a shopper sees in several chains has GS1 data. The single-chain tail (66% of items) has almost none.
- The serving code reads nutrition from the first column only (see `docs/gs1_integration.md`).

## 6. Risks
- **The GS1 benchmark is noisy and covers branded, multi-chain goods only (12%).** Accuracy on the single-chain tail is known only from hand samples until Dude grades the review sample.
- **Names are truncated** (about 20-character POS names such as "מרקיה צבעוני 25יח קר") and often brand-first. Some items cannot be classified from the name; the AI pass will hit the same limit.
- **Manufacturer data is 85% placeholders.** Brand facets and priors depend on GS1 brand or a new brand lexicon.
- **Keyword lists need upkeep.** Each new chain or brand adds vocabulary, and a broad negative can silently veto a category: in this session קרם on pantry and קוביות on meat did exactly that. The tests pin known names, and every rule edit should be re-run on the export.
- **Service and empty-name rows** (פיקדון, משלוח, 1,355 nameless items) pollute counts. They belong with the D1 pseudo-item rule, not in a category.
- **Taxonomy churn:** ids must stay stable once stored. v0 is a draft, so Dude's review comes before any table.
