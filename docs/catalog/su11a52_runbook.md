# SU11A-52 runbook — catalog categories v1 (for Dude)

Built 24 Oct 2026, **not applied and not deployed**. Nothing here changes the API, web or mobile: no code reads the new tables yet. Every step runs on the server as `dude` from `~/scrp`, except the migration (postgres superuser). Commands are copy-paste; outputs carry counts and names only, no secrets.

What is in the release:
- `db/migrations/su11a52_catalog.sql`: three new tables, `categories`, `item_categories` and `item_attributes`. They are additive and idempotent, applied in one transaction, and owned by `scrp_app`.
- `scripts/catalog/import_categories.py`: loads the taxonomy and the labels (since SU11A-56: taxonomy **v1.2**, `docs/catalog/taxonomy_v1_2.csv` + `gs1_group_map_v1_2.csv` + `brand_category_hints_v1_1.csv`; every v1 / v1.1 id kept, three added: D09.C11 still soft drinks, D16.C08 newspapers and magazines, D07.C08.S01 shelf-stable pickles and olives). Its default is a dry run; `--apply` writes everything in one transaction.
- `scripts/build_search_items.py` (daily timer, 14:30) has three changes:
  - service rows (פיקדון / משלוח / fees) are now hidden like coupons;
  - nameless items fall back to a chain name, then the GS1 name;
  - **new** live barcodes are classified into `item_categories` with source rule or gs1. Existing rows are never touched. The step skips with one warning while the tables are missing or `categories` is empty.
- **Precedence:** manual > ai > gs1 > rule.
  - An automated run never overwrites a manual row and never replaces a row of a higher source.
  - It never touches a row with `reviewed = true`.
  - The rule is enforced in the upsert SQL itself (`scripts/catalog/store.py`).

## 1. Apply the migration (sudo)

    cd ~/scrp && git pull
    cat ~/scrp/db/migrations/su11a52_catalog.sql | sudo -u postgres psql xxl_super -v ON_ERROR_STOP=1

Expected: `BEGIN`, `CREATE TABLE` ×3, `CREATE INDEX` ×3, `ALTER TABLE` ×3, `COMMIT`. Running it again prints NOTICEs ("already exists, skipping") and changes nothing.

Checks:

    sudo -u postgres psql xxl_super -c "\d categories" -c "\d item_categories" -c "\d item_attributes"
    sudo -u postgres psql xxl_super -c "SELECT tablename, tableowner FROM pg_tables WHERE tablename IN ('categories','item_categories','item_attributes')"

- All three tables are owned by `scrp_app`.
- `item_categories` has:
  - CHECKs on `confidence` (high / medium / low) and `source` (rule / gs1 / ai / manual);
  - an FK `category_id → categories(id)`;
  - the index `idx_item_categories_category`.
- There are no triggers.

## 2. Rebuild search_items once (new pseudo rule + fallback names)

Wait for the 14:30 timer, or run it by hand:

    cd ~/scrp && venv/bin/python3 -m scripts.build_search_items --apply 2>&1 | tail -40

Expected:
- `nameless items: {...}`, about 1,366 nameless, of which about 1,230 get a name from `item_chain_names` (local export of 24 Oct);
- `pseudo` grows by about 99 (the service rows);
- `"item_categories": {"skipped": "categories empty"}`, with one WARNING. That is correct before step 3.

Check: the `--report` mode lists the service rows under `deposit_first_word` / `delivery_first_word` / `fee_first_word`, with 40 sample names each:

    venv/bin/python3 -m scripts.build_search_items --report 2>&1 | grep -A3 "pseudo items"

## 3. Import taxonomy + labels: dry run, then apply

    cd ~/scrp && ulimit -v 2500000 && venv/bin/python3 -m scripts.catalog.import_categories --out /tmp/su11a52_dry.json

The dry run is read-only (a READ ONLY transaction). It prints JSON:

| Key | Expected |
|---|---|
| `categories` | `rows` 204, `insert` 204 (first import) |
| `item_categories_changes` | `{"insert": N}` on the first run |
| `planned_by_source_confidence` | counts per source and confidence (see section 6) |
| `unclassified_live_items` | the rest |
| `ai_labels_for_live_items` | how many AI labels match a live barcode today |

If the numbers look right:

    venv/bin/python3 -m scripts.catalog.import_categories --apply --out /tmp/su11a52_apply.json

The apply writes everything in one transaction and takes a few minutes. Then check:

    sudo -u postgres psql xxl_super -c "SELECT source, confidence, count(*) FROM item_categories GROUP BY 1,2 ORDER BY 1,2"
    sudo -u postgres psql xxl_super -c "SELECT c.name_he, count(*) FROM item_categories ic JOIN categories c ON c.id = split_part(ic.category_id, '.', 1) GROUP BY 1 ORDER BY 2 DESC"

A second dry run should report only `unchanged` (plus `protected` for anything you edited by hand).

## 4. Daily maintenance (nothing to do)

- The 14:30 build now classifies barcodes that have no `item_categories` row yet, by rules and the GS1 group. Its result JSON has an `item_categories` block (`new_live_barcodes`, `inserted`, `by_source_confidence`). A failure in that step logs a WARNING and never fails the search build.
- **Re-running the import later** (a new AI labels file, a new taxonomy version) is safe:
  - it updates rule / gs1 / ai rows only within the precedence rule;
  - manual and reviewed rows are reported as `protected` and left alone.

## 5. Your reviews → manual rows

**Done for the first review (SU11A-55):** `docs/catalog/review_graded_v1.csv` holds Dude's 150 graded rows (130 confirmed, 20 corrected, every id valid). Load it with the two commands below, using that file name. The local dry run reported `manual_rows: 150`, `manual_bad_ids: []`.

**Done for the AI audit (SU11A-57):** `docs/catalog/ai_audit_graded_v1.csv` holds Dude's 100 graded AI-only labels from `ai_audit_sample_v1_graded.xlsx`, with the four overrides (rows 46, 97 → D06.C04; 74 → D12.C12; 57 → D01.C01) and the free-text answers mapped to v1.2 ids as in `su11a56_v1_2_report.md` (rows 71 and 92 had no good node: nearest given, noted in `mapping_note`). item_code comes from `ai_audit_sample_v1.xlsx`. The local dry run reported `manual_rows: 100`, `manual_bad_ids: []`. Load it after `review_graded_v1.csv`:

    venv/bin/python3 -m scripts.catalog.import_categories --manual docs/catalog/ai_audit_graded_v1.csv            # dry run
    venv/bin/python3 -m scripts.catalog.import_categories --manual docs/catalog/ai_audit_graded_v1.csv --apply

The two files share no barcode, so the order does not matter for the result.

Fill `correct_category_id` (any id from `docs/catalog/taxonomy_v1_2.csv`) in any of:
- `docs/catalog/ai_audit_sample_v1.xlsx` (100 AI-only labels; has a drop-down; save it as CSV for the import);
- `docs/catalog/review_sample_v1.csv` (150 rows; already graded, see above);
- `docs/catalog/disagreements_v1.csv` (300 rows);
- `review_sample_v0.csv`.

Commit the file from Windows, pull on the server, then:

    venv/bin/python3 -m scripts.catalog.import_categories --manual docs/catalog/review_graded_v1.csv            # dry run
    venv/bin/python3 -m scripts.catalog.import_categories --manual docs/catalog/review_graded_v1.csv --apply

Each filled row becomes `source = manual`, `reviewed = true`, and no automated run touches it again. An id that does not exist is listed under `manual_bad_ids` and skipped.

## 6. Expected counts (taxonomy v1.2, local export of 24 Oct 2026; updated SU11A-56)

From the local export (131,324 live non-pseudo rows on 24 Oct; 99 of them become service pseudo rows, leaving 131,225). The server reads today's `search_items`, so expect the same shape with slightly different numbers.

**`planned_by_source_confidence`, about 129,070 rows** (v1.1 in brackets):

| Source | high | medium | low |
|---|---:|---:|---:|
| rule | 91,501 (91,529) | 3,186 (3,067) | 4,375 (4,378) |
| gs1 | 10,707 (10,801) | 163 (110) | 277 (279) |
| ai | 6,317 (6,330) | 3,933 (3,949) | 8,613 (8,629) |

The AI source is still `ai_labels_v1.csv` (Haiku): the SU11A-56 Sonnet pilot did not pass its gate, so no `ai_labels_v2.csv` exists.

**Other expected values:**

| Key | Expected |
|---|---|
| `unclassified_live_items` | about 2,150 (v1: 1,874; v1.1 and v1.2 the same). About 290 items that v1 called fresh fruit only because a fruit word appeared in the name (Skittles, jams, flavours) are now unclassified on purpose |
| `ai_labels_in_file` | 44,362 |
| `ai_labels_for_live_items` | slightly fewer (barcodes that left the catalogue since the export) |
| `item_attributes_planned` | about 90,000 rows: the server import of 25 Oct wrote **92,144** (corrected in SU11A-58; this line used to promise "several hundred thousand", an estimate that was never measured). See "Why item_attributes is about 0.7 rows per item" below |

**Low-confidence rows (13,265; v1.1 13,286; v1 13,704):** about 10,640 are rule-vs-AI disagreements (v1 11,100). The 300 most widely sold are in `disagreements_v1.csv` (regenerated for v1.2 in SU11A-56; it had no grades), ready for grading.

**New v1.2 nodes on the export:** D09.C11 still soft drinks about 270 items, D16.C08 newspapers about 55, D07.C08.S01 shelf-stable pickles and olives about 620 (D04.C05 keeps about 530). A facet UI should show high and medium only.

### Why item_attributes is about 0.7 rows per item (SU11A-58)

92,144 rows for about 129,000 labelled items. Nothing is wrong; the old estimate assumed two or three attributes per item. How the rows come about (`scripts/catalog/classify_rules.py` `extract_attributes`, called by `import_categories.py` `plan_labels`):

- **One row per attribute actually found**, not one per item and key. A yes/no attribute (organic, gluten_free, vegan, sugar_free, reduced, lactose_free, kosher_passover, weighted) gets a row only when it is true.
- **Only the keys the item's category offers** (taxonomy v1.2, inherited): brand, size_value, pack_count on all 204 nodes; kosher_level, kosher_type, kosher_passover, organic, gluten_free, vegan, sugar_free, reduced, flavour on the 131 food nodes; scent 18 nodes; weighted 16; fat_pct 14; lactose_free 14; alcohol_pct 14; state 10; cocoa_pct 4. Unclassified items get no attributes.
- **Read from the name only, plus two GS1 fields.** The import passes the GS1 brand and `items.is_weighted` and nothing else. It does not pass the manufacturer, GS1 kosher or GS1 diet, so: `brand` fills only for items with a GS1 brand name or a name that hits the brand-hint list (85% of live items carry a placeholder manufacturer anyway); `kosher_type` (פרווה / חלבי / בשרי) comes only from GS1 kosher and is therefore never written; kosher_level and the diet flags come from the name only.
- **size_value needs a number and a unit in the name** ("80 גרם", "1.5 ליטר"). Produce, weighed meat and fish, and names without a size get none.

Typical yields: "במבה אסם 80 גרם" → size only (no brand: Osem is not in the hints); "קוקה קולה זירו 6*1.5 ליטר" → size, pack, sugar_free; "עגבניות שרי במשקל" → weighted; "תפוח עץ" → nothing.

**Per-key coverage on the server** (read-only, seconds):

    # [Server — bash]
    sudo -u postgres psql xxl_super -c "SELECT attr_key, count(*) AS rows, round(100.0 * count(*) / (SELECT count(*) FROM item_categories), 1) AS pct_of_labelled FROM item_attributes GROUP BY 1 ORDER BY 2 DESC"

Passing the manufacturer and the GS1 kosher / diet fields into the import would add rows; that is a behaviour change for a later catalog session, not part of SU11A-58.

## 7. Rollback

Nothing reads the tables, so dropping them is safe at any time. The build then skips its category step with one warning.

    sudo -u postgres psql xxl_super -v ON_ERROR_STOP=1 -c "BEGIN; DROP TABLE IF EXISTS item_attributes; DROP TABLE IF EXISTS item_categories; DROP TABLE IF EXISTS categories; COMMIT;"

To undo the build changes (the service pseudo rule and the fallback names): `git revert` the feat commit, pull, and let the next build run (or run `--apply`). `--swap-back` restores the previous search build at once.
