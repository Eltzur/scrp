# SCRP — Project Handoff

> A living document. Update at the end of each session. Paste at the start of each new chat.
> Last updated: August 5, 2026 (end of session SU10A-6)

---

## 🎯 Vision

xxl.co.il is an Israeli multi-vertical savings platform. The supermarket vertical (super.xxl.co.il) is the anchor product — a clean, fast, accurate price comparison tool for Israeli grocery shoppers, powered by government-mandated transparency XML feeds.

**Near-term (6 months):** Match and exceed Cheapersal.co.il on data coverage, UX clarity, and location relevance. Every search result shows the branch name, address, and last update time. Promo prices highlighted where discount ≥10% or 2-for-1. Mobile-first responsive design.

**Medium-term (6-12 months):** Native mobile experience with barcode scanner — user scans a product in-store and instantly sees prices at nearby supermarkets within 500m radius, powered by store GPS coordinates from StoresFull XMLs. GS1 Israel integration for canonical product names, images, and nutritional data.

**Long-term:** AI-powered natural language search ("where's the cheapest cottage cheese near me?"), basket optimization across chains, and expansion to additional verticals (flights, hotels, fashion) under the xxl.co.il umbrella.

**Core principles:** data accuracy over coverage, location relevance over volume, mobile experience over desktop, free tier as the honeypot.

---

## 🏗️ Architecture

| Layer | Tech | Where | Status |
|---|---|---|---|
| Frontend | React + Vite + TypeScript + Tailwind | Kamatera nginx (PRIMARY for ALL xxl.co.il surfaces) — serves portal (xxl.co.il + www), super.xxl.co.il, and flights (fly.xxl.co.il). Portal & super share ONE build (web/dist). Hostinger (`82.198.227.247`) is COLD FALLBACK / DR only — older static copy, no live traffic. | ✅ Live |
| Backend | FastAPI + gunicorn + uvicorn | Kamatera `scrp-prod-il` via systemd `scrp-api.service`, behind nginx + Let's Encrypt | ✅ Live since May 18, 2026 |
| Database | Postgres 18.4 | Kamatera `scrp-prod-il` (`185.229.226.190`), localhost-only (5432 closed at UFW) | ✅ Live |
| Scraper cron | Python (`scraper.cron_main`) | Kamatera `scrp-prod-il` via systemd timer | ✅ Daily 10:00 IDT, DST-aware (changed from 03:00 in session 9n — portals publish 02:00–05:00 UTC; 10:00 IDT = 07:00 UTC clears the window) |
| Backups | pg_dump → rclone → Backblaze B2 | Kamatera systemd timer `scrp-backup.timer` (daily 04:00 IDT) + B2 bucket `xxl-scrp-backups` | ✅ Live since May 19, 2026 |
| DNS | box.co.il (ns1/2/3.box.co.il) | — | ✅ |
| Auth | Supabase | Supabase project (auth only — no Data API usage from client) | ✅ Live |

**Local dev:** `C:\scrp` on Windows 10/11. PowerShell + VS Code + Claude Code in VS Code terminal.

**Repo:** github.com/Eltzur/scrp (main branch is production)

**Production URLs:**
- Portal: https://xxl.co.il (and https://www.xxl.co.il)
- Supermarket app: https://super.xxl.co.il
- Backend: https://api-super.xxl.co.il
- Scraper/DB server (SSH only): `ssh dude@185.229.226.190` (Kamatera Tel Aviv, scrp-prod-il)

**Portal + domain hosting (Kamatera cutover, July 5 2026):**
- **Kamatera (`185.229.226.190`) is PRIMARY for ALL xxl.co.il surfaces**, including the portal. Hostinger (`82.198.227.247`) is COLD FALLBACK / DR only — it holds an older static copy and receives no live traffic.
- `xxl.co.il` + `www.xxl.co.il` are served by a Kamatera nginx block: `/etc/nginx/sites-available/xxl.co.il`, root `/var/www/super.xxl.co.il` (shared with super.xxl.co.il), SSL via certbot (cert expires 2026-10-03).
- DNS: A records at box.co.il for `xxl.co.il` and `www.xxl.co.il` → `185.229.226.190` (Kamatera). Cut over from Hostinger (`82.198.227.247`) on July 5, 2026.
- **Portal and super SHARE ONE React build (web/dist).** Because the xxl.co.il nginx block shares root `/var/www/super.xxl.co.il`, deploying web/ updates BOTH super.xxl.co.il and the portal (xxl.co.il / www) in one deploy.
- **Routing logic lives in React, NOT nginx/.htaccess.** `isPortalHostname()` in `web/src/utils/hostname.ts` checks `window.location.hostname` and renders `PortalPage` at `/` when on xxl.co.il, else renders `AppShell` (supermarket app).
- **DR revert path:** repoint the `xxl.co.il` + `www` A records at box.co.il back to `82.198.227.247` (Hostinger cold copy).

**Key infrastructure commands:**

*Kamatera (all production infra):*
- SSH: `ssh dude@185.229.226.190` (or `ssh root@...` via key for admin)
- API service: `systemctl status scrp-api.service` (gunicorn on 127.0.0.1:8000, nginx proxy on 443)
- Reload API: `systemctl restart scrp-api.service`
- nginx config: `/etc/nginx/sites-available/api-super.xxl.co.il` (managed by certbot)
- Manual scrape: `cd ~/scrp && venv/bin/python -m scraper.cron_main`
- Scheduled scrape: `systemctl start scrp-cron.service` (daily 03:00 IDT timer)
- Scrape logs: `journalctl -u scrp-cron.service --since "yesterday" | tail -50`
- API logs: `journalctl -u scrp-api.service -f`
- Postgres console: `sudo -u postgres psql xxl_super`
- Cert renewal: auto via `certbot.timer` (next ~02:30 IDT daily), expires 2026-08-16
- UFW open ports: 22, 80, 443
- Manual backup: `systemctl start scrp-backup.service`
- Backup logs: `journalctl -u scrp-backup.service --since "yesterday"`
- List B2 backups: `rclone ls b2:xxl-scrp-backups/daily/`
- Restore (scratch DB): `sudo -u postgres createdb test_restore && sudo -u postgres pg_restore -d test_restore /var/backups/scrp/xxl_super-YYYY-MM-DD.dump`

**Folder layout (matters because some folders are misleadingly named):**
- `web/` — React frontend (NOT the backend, despite the name)
- `api/` — FastAPI backend
- `scraper/` — scraper code + cron entrypoint
- `db/` — schema, migrations, helper scripts
- `frontend/` — empty stub, leftover from skeleton commit, ignore

**Frontend deployment (Kamatera):**
- Deploy via `scripts/deploy_frontend.ps1`: build `web/` → scp `dist/` to `/var/www/super.xxl.co.il` on Kamatera. This updates BOTH super.xxl.co.il AND the portal (xxl.co.il / www) because the xxl.co.il nginx block shares that root.
- SPA routing (React Router fallback) is handled by the nginx `try_files` fallback in each server block; hostname routing is handled in React (`isPortalHostname()`).
- **Legacy (dead):** the old Hostinger path (build → zip `dist/*` → upload+extract in `public_html/`) is retired. Hostinger holds only a cold DR copy and receives no live traffic.

---

## 📊 Current Production State

**Last updated: August 5, 2026 (end of session SU10A-6)**

- **14 chains** in registry: Shufersal, Rami Levy, Osher Ad, Victory, Yochananof, Keshet, Carrefour, Tiv Taam, King Store, Shefa Birkat Hashem, Shuk Hayir, Fresh Market, Super Yuda, חצי חינם / Hazi Hinam (added 9d-9)
- **~1,200 stores** in active_stores.yaml (post 9d-9 additions: Rami Levy +72→98, Yochananof +35→50, Keshet +12→22, Osher Ad +11→23, Hazi Hinam +1→12; Paz + Dor Alon removed in 9d-8)
- **city_canonical** is the source of truth for all city data (rebuilt from CBS 2024 in 9d-8, 0 NULLs). city_norm is legacy/broken — do not use.
- **Delta mode active for ALL 14 chains** (SU10A-6 added the last 6: Tiv Taam, Carrefour, Victory, then King Store, Shefa, Shuk Hayir). Controlled by `DELTA_CHAINS` in `registry.py` + `uses_delta()`. **Delta mode has no periodic PriceFull resync** — the base class only falls back per-store when a delta file is missing, so a missed cron day silently loses that day's changes until someone runs `run_one <chain> --full`.
- **Per-store parallelism**: `STORE_WORKERS=4` in `base.py` and `shufersal.py`. Each worker opens its own DB connection. Shufersal: 4436s → 544s (8×). Tiv Taam: 6913s → 93s (74×).
- **Chain-level parallelism**: `cron_main.py` ThreadPoolExecutor(max_workers=6). Full cron target: <30 min (to be confirmed by next 10:00 IDT run).
- **City dropdown**: 0.13s response (was 3.7s — prices JOIN removed in 9d-8).
- **Verification gate**: `active_stores.yaml` (verified to publish PriceFull/Price) is what cron uses; `scheduled_stores.yaml` is the wish-list. See `db/verification_report_9d1.md` for excluded stores.
- **GS1 Israel catalog**: ✅ LIVE (SU10A-1/2, July 2026). Own `gs1` schema on the same Postgres. **22,559 products across 77 suppliers**; **11,496 carry full per-product detail** (`gs1.products.full_content` JSONB — kosher/Kashrut certification 100%, media assets 100%, ingredients 97%, nutrition panel 67%); **11,450 product images** fetched and resized (800px/JPEG-80, 0.62 GB). Incremental sweep is wired into the nightly cron, exception-wrapped so a GS1 failure never fails the supermarket scrape. Counts drift upward nightly — re-query rather than trusting this line.
- **✅ GS1 phase-2 data is now customer-facing (SU10A-4).** Images and the kashrut / nutrition / ingredients / allergens blocks all reach users through the product detail modal, alongside the product name. Two endpoints serve it: `GET /product/{item_code}/details` (200 with `has_gs1_data: false` and null sections for the ~91% of items with no GTIN match — a normal case, not an error) and `GET /product/{item_code}/image`.
  - *Historical context for why the image path looks the way it does:* the images still sit in `~/gs1_images` on the VPS as loose `dude`-owned files, with no nginx route, no web root, no URL scheme and no `product_image_url` column populated — `www-data` cannot read `~dude`. Rather than relocating ~11.5K files, the API serves them directly: the filename is the GTIN and the GTIN is the item_code, so it resolves with a `stat()` and no DB hit. That permission gap is worked around, not closed, so a future move to nginx/CDN serving is still an open option.
- **Canonical names**: ✅ RESOLVED (was "blocked on GS1 IL access" — that access is live and the pipeline has run). Weighted token voting (session 8b) plus GS1 enrichment both write `items.item_name`; **10,585 items are stamped `name_source='gs1'`**. SU10A-3 also fixed the display bug that made this invisible: the API was showing one chain's arbitrary raw scrape instead of the computed canonical name, so **87% of the GS1 enrichment was landing in the DB and never reaching a user**. Both ranking and display now read `items.item_name`.
- **Search** ranks by relevance tier (item_name prefix → whole word → substring → manufacturer-only), then multi-chain, then cheapest, then `item_code` as a deterministic tie-break. **Numeric and percentage tokens are NOT filtered** — they are product attributes and were previously discarded, silently widening every sized query (SU10A-3 reversed this; the old "tokens filtered" behaviour from session 8b is gone). `חלב 3%` narrows to 3% milk; `במבה 80` narrows to 80 g. Bare numbers match on a digit-run boundary so `80` does not match inside `180`. **Length < 2 is the only remaining token filter.**
- **Promos**: ✅ REBUILT AND RESOLVED (SU10A-5) — previously flagged "CRITICALLY BROKEN" on a premise that did not survive audit. A UNIQUE (store_fk, item_code, promo_id) constraint makes duplicate rows structurally impossible; the large per-chain counts are legitimate per-store fan-out. **All 14 chains are now populated** (~560K rows, up from 274K) after onboarding the 4 that produced none. Discounts are computed at READ TIME in `db/query.py` — never stored — so unit semantics stay fixable without re-scraping. Served by `GET /promos/grouped` (chain → city → branch, no dedup, no cap). **Never key promo logic on `reward_type` / `DiscountType` / rate or `min_qty` units without per-chain verification** — all three vary by chain.
- **Known coverage gap**: Bnei Brak has no Carrefour/Yenot Bitan/Mega presence (verified via carrefour.co.il store locator) — accepted, not a bug.
- **Live site status**: ✅ super.xxl.co.il + xxl.co.il fully operational, all API calls served from Kamatera over HTTPS.

---

## ✅ Sessions Completed

### Session SU10A-5 (August 2, 2026) — city_canonical_review.csv reconciled + promo pipeline rebuilt (all 14 chains live)

**City CSV — resolved.** The "three divergent versions" was largely illusory: the server's uncommitted 1,078-row/9-col file and the reverted c3833a0 were byte-identical apart from CRLF vs LF. Committed the 1,078-row/9-col builder output as baseline (ec1142d) — two builder-versions newer than the old 890-row/7-col version, carrying 13 hand-entered action=delete review decisions that existed nowhere else. Provenance: an undocumented June 2 re-run of build_city_canonical.py (after 256bf68 added chain_id) plus a manual review pass; pinned by git timeline. DB check: all 13 delete-marked stores are already absent from stores — deletes effected, nothing pending. NOTE: the CSV's store_id column is actually stores.id, not stores.store_id.

**Promos — the "60K corrupt Victory rows" narrative was FALSE.** A UNIQUE (store_fk, item_code, promo_id) constraint makes duplicate rows structurally impossible; Victory's 148K rows are legitimate per-store fan-out and among the cleanest data we have. The real defects: (1) 4 chains produced zero promos — the 3 BinaProjects chains (King Store, Shefa, Shuk Hayir) raised NotImplementedError and HaziHinam parsed to zero (variant schema); (2) three unit-mismatch bugs, each caught by a dry-run gate — Rami Levy encodes MinQty as agorot (5990=₪59.90), HaziHinam encodes DiscountRate as basis points (5000=50%), and reward_type is chain-specific (Victory 1+1 = reward_type 10) so it must never be branch logic; (3) the display collapsed per-branch rows via DISTINCT ON and masked garbage with a ≤99% cap.

**Shipped:** new GET /promos/grouped endpoint with discount computed at READ TIME (store raw, stay re-fixable), min_qty-aware, uniform rate>100→/100 basis-points normalization, 0–100 guard, active-only, online-store filter, no dedup/cap (5ef8bc8, d57f728, 20a9ec5, d2afb1c). Grouped chain→city→branch frontend; city logic extracted to web/src/utils/city.ts shared with HomePage. One shared variant parser parser/price_parser.py::parse_promo_file_flat covering Bina+HaziHinam (shared parse_promo_file untouched); PROMO_PARSER hook in base.py. All 14 chains now populated — promos table 274K→560K rows; promo_type populated for the first time (new rows only). db/migrations/su10a5_promos.sql (450cdc1) formalizes the previously ad-hoc table with GRANT incl. the sequence USAGE/SELECT. Dead PROMO_CHAINS/uses_promo() removed (ccd0b56) — never called, and it had falsely named the 4 empty chains as promo-enabled for months, which made this look like a config problem.

**Principle:** store promo fields raw, compute discounts at read time; never key promo logic on reward_type/DiscountType/rate/min_qty units without per-chain verification.

**Carried forward:** King Store 68% catalog match (~1,200 promoted item_codes not in items → bare barcode); 4,091 weighted-goods rows (min_qty<1) excluded — the fresh-produce/meat/fish gap; promo_type still NULL on the original 10 chains (cosmetic). Parser adds still owed for club-only, max-qty, and gift-item-count ("3 for 2") signals.

---

### Session SU10A-5 (continued, Aug 2–3 2026) — promos UX, promo-in-search, GA4 fixed

**Promos UX (/promos).** Added: chain-gated branch filter (enabled only when one chain is selected); multiselect discount bands as ranges (0-10 / 11-25 / 26-50 / 51-75 / 76-99 — gifts at 100% are reachable only via the promo-type chip, since bands stop at 99); promo-type chips derived from SHAPE not reward_type (gift = discount_price 0; bundle = min_qty 2-24 & price>0; fixed = min_qty 1 & price>0; discount = rate-only; basket = min_qty>24 / no unit price); sort (discount / savings / ending); ending-soon filter; item search bar; basket cards (conditional/spend-threshold promos shown with description + condition badge, no fabricated unit price). Backend /promos/grouped gained params branch, bands, promo_type, q, ending_within_hours, sort and returns promo_kind. Commits 08f9eb9 (backend), 6c399a7 (frontend), e8f693b (store_fk added for branch filter). Surfacing basket rows partially closes the fresh-produce gap (weighted goods now visible with real terms in the description).

**Promo-in-search (main super search leads with best price).** Promos attach at (store_fk, item_code) BEFORE the per-chain collapse, via a DISTINCT ON LATERAL picking the single lowest comparable unit price per store+item — a plain LEFT JOIN would duplicate rows (2% of store+item pairs have >1 active promo, max 12) and distort cheapest/chains_count. Comparable classes ranked: direct single-unit (min_qty=1), rate-only single-unit, bundle (min_qty 2-24, unit=price/qty). Basket (min_qty>24) and junk barcode 0000000000000 never rank. Attach only when promo unit < that store's shelf. effective_price = LEAST(shelf, promo_unit) drives per-chain min, cheapest, sort, delta. Bundles DO rank (Option A, Dude's call) but always render with the condition + branch so a "₪4 that needs buying 3" never masquerades as a single-unit price. Commit 167a9a3 (backend; group_by_store fixed too), frontend in 6c399a7 area (ProductCard: struck shelf, מבצע badge, condition label, branch name). ~10,959 items (~8%) have a qualifying promo (~1 in 11 results); perf +11-14% warm, within budget. DEFERRED: promo-only items (a promo at a store with no shelf price row — ~86% of item+chain pairs) do not appear in search (search is price-row-driven) — the biggest remaining coverage lever.

**Promo unit-mismatch lesson (reinforced three times).** Never key promo logic on reward_type / DiscountType / discount_rate scale / min_qty units without per-chain verification: Rami Levy stores MinQty as agorot (5990=₪59.90); HaziHinam stores DiscountRate as basis points (5000=50%); Victory encodes 1+1 as reward_type=10. Store raw, compute discounts at read time.

**Promo-in-search is geographically uneven.** Promos average only 2-4 stores per chain, so the best-price benefit is thin in promo-sparse cities — structural, and the main argument for doing the promo-only-items work.

**GA4 — was never collecting; now fixed and verified end to end.** Two real code defects: (1) the first page_view was never sent (config used send_page_view:false and nothing re-called trackPageview after consent) — so accept-and-read-one-page sent zero; (2) a consent dead-state trap — CookieBanner rendered only when the key was ABSENT (===null) while the GA gate required ==='true', so clicking decline ('false') left GA permanently off with no banner to re-prompt. Fixes: send the first page_view at the end of initGA(); trackPageview now uses pathname+search and re-checks consent at SEND time (a withdrawal stops reporting); openCookiePreferences() re-entry control on the privacy page + a footer "עוגיות" link. Super commits include 8f7d81f. VERDICT: both the site tag AND the GA property are correct — proven by a server-side Measurement Protocol hit appearing in DebugView (validationMessages [], HTTP 204). Every "No data received" was CLIENT-SIDE blocking: the dev desktop browser had privacy extensions swapping GA for a stub (network trace showed googletagmanager gtag/js 200 alongside a chrome-extension surrogate google-analytics_analytics.js, and google_tag_manager stayed undefined), and the phone browsers blocked it too (Mi Browser built-in blocker / Android Private DNS). CSP ruled out (no CSP header/meta anywhere). GA undercounts blocked users by design — nginx access logs are the true, unblockable traffic count. Measurement ID G-YB4X4E5ZKM. Flights (fly.xxl.co.il) wired into the SAME property (ac5e19c); all three surfaces (xxl.co.il, super, fly) separate by hostname. Note: flights .env.production is git-tracked and now holds the GA ID + Supabase anon key — both are public client values so this is acceptable, but a Supabase service-role key or any real secret must never go there.

**Promo-only-in-search (2b) shipped:** search injects promo-only quotes (store with a comparable promo but no shelf row for that item) so it leads with the true cheapest. _PROMO_ONLY_SQL(_CITY) run as separate statements (DISTINCT ON needs its own ORDER BY → no UNION ALL), concatenated into fetch_prices' row list under the same store_fks/chain filters; item_price NULL, _effective falls to promo_unit, promo_kind='promo_only', LEFT JOIN item_chain_names with items.item_name fallback (41% lack icn). Direct+bundle only (rate-only needs a shelf, excluded). PERF GOTCHA: the NOT EXISTS anti-join needs a nested-loop plan, which collided with fetch_prices' SET LOCAL enable_nestloop=off (9d-8 price-query optimization) → 12× regression; fixed by running the promo-only statement BEFORE the SET LOCAL. ProductCard renders promo-only quotes with no strikethrough. SCOPE CORRECTION: the '86% promo-only gap' was mostly illusory — of truly-invisible items only 83 are nameable; ~2,250 aren't in `items` at all, so surfacing them is catalog enrichment (King Store task), NOT search injection.

> **Correction to the perf note above, from the shipped fix:** running the promo-only statement *before* the `SET LOCAL` is NOT sufficient. `SET LOCAL` lasts for the **transaction**, not the statement, so on the second and later `fetch_prices` calls on one connection the flag is already off and the ordering achieves nothing (measured: call 1 817ms, call 2 8734ms). The shipped fix toggles explicitly per statement — `enable_nestloop = on` before the promo-only query, `off` before the price query. Final cost 596ms → 617ms (+3.6%). Also note **compare mode (the default) hides promo-only-only products**, since they have `chains_count = 1`.

**Carried forward (open):** promo-only items in search (~86% gap); King Store 68% catalog match (~1,200 promoted item_codes not in items → bare barcode); fresh food / weighted goods (min_qty<1) into search; parser adds owed (club-only, max-qty, gift-count for "3 for 2").

> **Superseded by SU10A-6 (measured):** the real figure is 60,275 orphaned promoted item_codes for King Store — 68.7% of its 87,771 promoted codes have no items row, ~50× the "~1,200" and ~27× the "~2,250" recorded here. Earlier figures likely used a different denominator (search-reachable items, not all promoted codes); not reconstructable from the note. 96.8% of sampled 13-digit codes are checksum-valid EAN-13 — real products King Store promotes but never publishes a shelf price for, not junk data. King Store alone is ~93% of all orphaned promoted codes across the 14 chains.

---

### Session SU10A-6 (August 4-5, 2026) — cron killed mid-run (8 "stale" chains diagnosed), delta extended to all 14, Cerberus + Bina field-name fallbacks

**The "8 failing chains" were not failing.** 8 chains last loaded Aug 2 and looked broken. There is not one `FAILED` line, traceback, or per-chain error anywhere in the Aug 2-4 journal — the Aug 2 coverage report shows `0 errors` on all 14. The cron *process* was SIGKILLed mid-download: Aug 3 died 1h55m in, Aug 4 died 4h03m in (`Result: signal`, `ExecMainStatus=9`), so no coverage report was ever emitted on either day. `fetch_runs` shows the signature — chains that finish before the kill are `ok`, chains in flight are stuck at `status='running'` with 0/0/0, and chains scheduled later have no row at all. **The 8 "stale" chains were simply the 8 that run last.** Prior 8 days all completed in 13,828-19,314s (3.8-5.4h). Timer, disk (56%), and all portals were healthy and are not implicated.

**SIGKILL cause is still UNCONFIRMED.** `kernel.dmesg_restrict=1` and `/var/log/kern.log` is `syslog:adm 0640`, so the kill record needs sudo (which prompts for a password over non-interactive SSH — plain `journalctl -u scrp-cron` works fine for `dude` and needs no sudo at all). Prime suspect is the kernel OOM killer: 1.9 GiB box, `shared_buffers=512MB`, several *idle* `scrp_app` Postgres backends at ~600 MB RSS each, and `MemoryMax=infinity`/`OOMPolicy=stop` on the unit so an OOM lands as a raw SIGKILL. Settle it with `sudo journalctl -k --since ... | grep -iE "out of memory|oom-kill|Killed process"`. Note `TimeoutStartSec=infinity` in the drop-in, so it is definitively NOT a systemd timeout.

**Fix 1 — Cerberus field-name fallback (9ce86b4).** `parse_file()` matched `ManufacturerName`/`PriceUpdateDate`; the Cerberus delta feed publishes `ManufactureName`/`PriceUpdateTime`. Reused the existing `_first_text()` (already in the same file for the Bina flat promo parser) rather than duplicating it. Proof it works: after re-running, non-NULL `price_update_date` equals items inserted *exactly* — Tiv Taam 478,172 total − 164,038 NULL = 314,134 = items inserted; Victory 614,651/614,651. Every chain still on the old parser sits at 94-100% NULL, every re-run chain dropped sharply.

**Fix 2 — promo upsert (9ce86b4).** Deleted the `DELETE FROM promos WHERE store_fk=:fk` that ran before every promo insert in `base.py::_process_store`. `bulk_insert_promos` is a genuine upsert (`ON CONFLICT (store_fk,item_code,promo_id) DO UPDATE` on all 10 fields, plus in-batch dedup), so duplicates were structurally impossible and the DELETE was only wiping a store's whole promo set on every partial file. Verified safe to drop: **all 447,663 promo rows have a non-NULL `promo_end`**, and every read path in `db/query.py` filters `(promo_end >= NOW() OR promo_end IS NULL)` — so the rows that now linger are unreachable from the API and the `IS NULL` branch is dead code in practice. Residual is housekeeping only: 15,169 expired rows (3.4%) now accumulate; an occasional `DELETE FROM promos WHERE promo_end < NOW() - interval '30 days'` caps it.

**Fix 3 — delta for Tiv Taam / Carrefour / Victory (9ce86b4).** `build_price_index`/`build_promo_index` already existed for all three; only the `DELTA_CHAINS` membership was missing. Verified: Tiv Taam 46/46 files 314,134 items 0 errors 279s; Carrefour 87/87 383,747 items 0 errors 383s; Victory 69/69 614,651 items 0 errors 822s. **These three consumed ~2h20m of the Aug 4 cron and now take 24 min combined** — which should pull the run well inside the window where it was being killed. That is mitigation, not diagnosis.

**Fix 4 — Bina Projects delta support (aa95f32).** Probed `MainIO_Hok.aspx`: **WFileType 1=StoresFull, 2=Price (delta), 3=Promo (delta), 4=PriceFull, 5=PromoFull, 6+ return nothing.** Added `build_price_index` → `_build_file_index(ids, "2", "Price")` and switched `build_promo_index` from `"5"/"PromoFull"` to `"3"/"Promo"`. The `"Price"` prefix cannot cross-match `PriceFull` — the pattern is `^{prefix}{CHAIN_ID}-(\d+)-(\d{12})\.gz$`, so the chain id must follow the prefix immediately. King Store/Shefa/Shuk Hayir moved into `DELTA_CHAINS`; **all 14 chains are now delta.** Delta coverage is identical to PriceFull coverage (28/30, 22/30, 19/20) — the skipped stores are the same chronic no-file stores from 9d-10, including Shefa's 8 known promo-only branches, not a delta regression. Bina files are ZIP despite the `.gz` extension (`PK` magic) — the scraper already handles both.

**Fix 5 — `ItemNm` (aa95f32).** Bina publishes the product name as `ItemNm`, and **this is true of PriceFull as well as the delta feed**, not just delta. Confirmed by sampling a live file: `PriceFull7290058108879-340` carries `ItemNm` on all 2,364 items with **zero** missing, alongside a standard `ManufacturerName`. That asymmetry explains the whole picture — the old parser matched `ManufacturerName` fine but missed the name, so the 3 Bina chains sat at ~84% NULL `item_name` while every other chain was at 0.0%, and every *delisted* Bina item left a permanent row with manufacturer set and name NULL.

**Catalog backfill.** A `run_one <chain> --full` pass on the 3 Bina chains under the fixed parser (King Store 28/28 146,325 items; Shefa 22/22 60,775; Shuk Hayir 19/19 81,837; all 0 errors) dropped their `item_chain_names` `item_name` NULL rate 84%→21-28% and `manufacturer_name` to 0.0%, and closed their Aug 3-4 data gap. Then one `UPDATE items ... FROM item_chain_names`: **`items.item_name` 12,744→4,978 NULL, `items.manufacturer_name` 79,294→54,056**, with 0 rows left backfillable afterwards.

**STRUCTURAL GOTCHA — re-scraping never repairs `items`.** `bulk_insert_items` is `ON CONFLICT(item_code) DO NOTHING` ("first writer wins canonical name", `db/db.py`), so once an `items` row exists with a NULL field it is **frozen** no matter how many times the chain is re-scraped. Only `item_chain_names` refreshes (`DO UPDATE`). **Any future parser field fix therefore needs an explicit SQL backfill to reach `items` — the scrape alone will not do it,** and judging a parser fix by an `items` NULL count will read as failure even when the parser is correct. Measure per-chain on `item_chain_names` instead.

**Carried forward (open):** (1) **SIGKILL cause unconfirmed** — one `sudo journalctl -k` settles it; tomorrow's cron is the real test of whether delta alone fixed it. (2) 7 chains are still 94-100% NULL `manufacturer_name` in `item_chain_names` because they have not re-run since Fix 1 (Shufersal, Super Yuda, Osher Ad, Hazi Hinam, Fresh Market, Rami Levy, Yochananof) — **re-run the same backfill UPDATE after the next cron** to clear most of the remaining 54,056. (3) Delta has no periodic PriceFull resync (see Current Production State). (4) Fresh Market promos are 1,525/1,525 expired, 0 active. (5) Tiv Taam yields only 323 promos across 46 stores (~7/store) vs Carrefour 16,955 and Victory 72,828 — its promo index reports "54 stores available, 1 targeted" on every store; looks like a Bina-style index bug, unrelated to this session's changes. (6) The 4,978 residual NULL `item_name` are item codes with no name published by any chain — nothing left to extract. (7) **King Store catalog-completeness gap** — 60,275 orphaned promoted item_codes (68.7% of its promoted codes), no `items` row / no name / not in search. Split: 52,510 valid EAN-13, ~4,756 internal PLU, rest unpadded/ITF-14. **Both candidate explanations were measured this session, so do not re-run them:** only **5,372 (8.9%)** match a GS1 GTIN — GS1 is the sole name source and covers under a tenth; and un-scraped stores are **ruled out** — only 3 King Store branches are un-scraped (000, 050, 338), and 338's PriceFull shares **0 of 2,088** codes with the orphan set, so these products are never price-published anywhere in the chain. Realistic ceiling is therefore ~5,372 nameable products, not 60,275 — and even those need a synthetic price row or a promo-only search path, since search is price-row-driven. GS1 gives names only; only store-coverage expansion yields search presence, and there is no store coverage left to expand here.

---

### Session 9d-10 (June 9-14, 2026) — Store Seeding Fixes + Search Performance + Geolocation + Promo Failure

> **Superseded by SU10A-5:** the "60K corrupt" framing was wrong — see SU10A-5. The rows were legitimate per-store fan-out, not duplication.

#### Completed
- publishprice.py regex bug fixed (subchain vs store_id capture). Carrefour: 59→148 seeded stores, 380K→827K prices.
- Carrefour padding normalization: duplicate rows (0002/002) merged via scripts/fix_carrefour_padding.py. 91 rows merged.
- Victory scraper rewritten to new laibcatalog REST API (old /webapi endpoint was 404). Victory: 17→69 stores, 604K prices.
- Shefa 8 physical stores confirmed promo-only (no PriceFull). Leave in yaml, mark as chronic no-file.
- Shufersal stores 413 (ONLINE) and 844 (Express Ramat Gan) added to active_stores.yaml and seeded.
- scripts/seed_one_store.py added for targeted single-store seeding.
- Cron post-run coverage report added to cron_main.py.
- Search performance: 14s→0.28s cold, ~0.1s warm.
  * Root cause: missing idx_prices_store_fk index + stale statistics + nested loop query plan
  * Fix: ANALYZE prices, covering index idx_prices_item_store_cover, two-step store_fk pre-fetch in fetch_prices(), SET LOCAL enable_nestloop=off
  * Migration: db/migrations/9d10_perf_indexes.sql
- IP geolocation city auto-detect on page load (ip-api.com). localStorage persistence for returning users. Eliminates all-cities cold query.
- API warmup ping on page load (/health) to eliminate gunicorn cold start.
- docs/xxl-stack.md created — technical reference for CC (schema, conventions, common mistakes).
- Victory promo CardinalityViolation fixed: bulk_insert_promos now deduplicates by (item_code, promo_id) before upsert.

#### Failed / To Be Rebuilt from Scratch
- **Promo pipeline: CRITICALLY BROKEN.** Victory DB has 60K+ active promo rows (impossible — real store has ~500-1000 promos). Shufersal promo data also suspect. Root causes unknown but likely:
  1. Promo parser inserting duplicate rows across stores incorrectly
  2. item_code matching between promos and prices tables is wrong
  3. discount_pct calculation logic is fundamentally flawed for Israeli promo formats
  * Promo display: NOT SOLVED. Promo table data is corrupt/inflated (Victory 60K+ rows, dedup bug). Frontend promo badges non-functional. Full audit and rebuild required — do not attempt incremental fixes. Deferred.
  * מבצעים חמים page: exists at /promos but shows garbage data
  * ALL promo work needs investigation and rebuild in a dedicated session
  * DO NOT attempt incremental fixes — start fresh with promo data audit

#### Deferred
- P3: Store address columns (ALTER TABLE + ingest_store_address.py) — not started
- Shefa 8 promo-only stores: decide whether to remove from active_stores.yaml
- Carrefour store 006 cleanup: DONE (store was already absent from yaml — no action needed)
- פומלית in פסטרמה results: token matching bug, documented, deferred
- Victory promo deduplication (60K rows): needs full promo table audit and re-seed

#### Known Issues Carried Forward
- Promo table data is corrupt/inflated — do not use promo data until audited
- CC must always git push after every commit (added to CLAUDE.md)
- Cron runtime now ~70+ min due to expanded store count

---

### Session 9d-11 (June 14, 2026) — Carrefour Cleanup + GS1 Scoping

#### Completed
- Carrefour store 006 removal: no-op — store was already absent from active_stores.yaml (cleaned in prior session)
- docs/gs1_integration.md created: full GS1 integration scoping document (schema, API changes, scraper enrichment flow, rollout plan, risk register, open questions). SCOPING ONLY — no implementation.

#### Pivoted
- GS1 path deprioritized (slow response from GS1 IL). Investigating Cheapersal catalog scraper as alternative product data source.

#### Deferred
- GS1 integration implementation: blocked on GS1 IL reply + decision gates (see docs/gs1_integration.md Phase 0)

---

### Session SU10A-1 (July 26-27, 2026) — GS1 API access unblocked (auth confirmed working, root cause was local)

**Status change from 9d-11:** GS1 IL access is no longer blocked. Registration completed and paid (₪2,950, invoiced 07/07/2026, signed 23/06/2026 under Elad Tzur, GLN 7292117800007). External-user + access-delegation forms on file in `GS1/` (gitignored, not in repo history). GS1 gave API credentials (account `xxlmain`) this session.

**Confirmed working, end to end:**
- Domain: `https://hq.gs1ildigital.org` — real, live, Cloudflare-fronted, Symfony backend. This is the ONLY confirmed-working domain for the search endpoint.
- **Not our domain:** `fe.gs1-retailer.mk101.signature-it.com` (the doc's example for GET PRODUCT/media/fieldInfo endpoints) does not resolve at all — dead or was never real; "mk101" is another client's account code left in a templated doc. ~~`retailer.gs1ildigital.org` (the web UI you log into manually) is a completely different app — hitting the API path there returns a Symfony 404, not our endpoint.~~
  - ⚠️ **CORRECTED 2026-07-28 (SU10A-2): the strikethrough above is WRONG and cost the next session a wrong turn.** `retailer.gs1ildigital.org` **does** serve the external API, on the same HTTP Basic Auth credentials as `hq.gs1ildigital.org`. Both of these returned **200 with real data** when probed directly:
    - `GET https://retailer.gs1ildigital.org/external/product/{product_code}.json?hq=1` — the full product detail record (17 sections incl. Kashrut, ingredients, allergens, nutritional values table, dimensions).
    - `GET https://retailer.gs1ildigital.org/external/product/{gtin}/files?media=all&default_image=1&hq=1` — product imagery.
    The original 404 was presumably from a different path, or from before the credential casing bug was fixed. **Do not treat this domain as dead.** See § SU10A-2 for the field shape.
- Auth mechanism: HTTP Basic Auth, confirmed via `WWW-Authenticate: Basic realm="Secured"` on the 401 challenge.
- Endpoint verified live: `POST https://hq.gs1ildigital.org/external/app_query/select_query.json` with a `modification_timestamp` query returns real cross-supplier product data (verified against GLN 7290000200002, brand טיב טירת צבי).
- Credentials stored server-side in `~/scrp/.env` as `GS1_USERNAME` / `GS1_PASSWORD` (uppercase — pre-existing before the new lowercase-default convention below; left as-is since it's now verified working, not touched to avoid re-breaking it).

**Root cause of the entire day's "401 / IP not allowlisted / wrong auth" investigation:** a casing mismatch. `.env` had `GS1_Username`/`GS1_Password` (mixed case); every test script referenced `$GS1_USERNAME`/`$GS1_PASSWORD` (uppercase). Bash variable names are case-sensitive, so `source` set the mixed-case variables with zero error while the uppercase ones stayed empty — every "failure" for most of the session was actually an empty/wrong-case credential locally, not a GS1-side block. Cost a full session of misdirected diagnostics (IP-allowlist theories, domain-guessing, PowerShell/curl quoting deep-dives) before being caught by explicitly dumping the raw `.env` bytes and comparing sourced-vs-typed-inline credentials side by side.

**New policy (added to CLAUDE.md):** default new env var names to lowercase going forward; always verify exact casing in the file before referencing a variable in a script, never assume.

**Also fixed along the way (real bugs, not red herrings):**
- `.env` line 1 (`DATABASE_URL`) had a stray leading `=` from a bad manual edit — fixed (typo, per Dude).
- `.env` used `:` instead of `=` for the GS1 lines on first attempt — fixed.
- Unquoted `$` in `GS1_PASSWORD` was getting partially expanded by `source` — fixed by single-quoting the value.

**Not yet done — next session:** build the actual fetch/storage pipeline for the 72 approved vendor catalogs (original ask this session) — sweep by `modification_timestamp` across all connected suppliers, paginate via `get_chunks`, store raw + parsed records keyed by GTIN in a new schema (mirrors the `flights` schema-on-same-Postgres pattern), join path back to existing `items`/`item_code` tables per the GS1 scoping doc from 9d-11 (`docs/gs1_integration.md`). Also: let GS1's support contact know the issue resolved on our end, no IP allowlist or password reset needed after all.

---

### Session SU10A-2 (July 27-28, 2026) — GS1 phase-1 catalog pipeline shipped end to end

Delivers the pipeline SU10A-1 scoped as "next session". Fully isolated: no scraper or city-resolution code was touched.

**Shipped:**
- **Schema** (`db/migrations/su10a1_gs1_catalog.sql`, + `su10a1b_gs1_gln_consolidate.sql`) — new `gs1` schema on the same Postgres, mirroring the `flights` schema-on-same-DB pattern. `gs1.products` (catalog rows, `product_code` UNIQUE, indexed on `gtin`/`gln`/`modification_timestamp`) and `gs1.sync_runs` (watermark + run status). Both migrations carry explicit `GRANT ... TO scrp_app` per the 9d-2 lesson — migrations run as postgres superuser, the app connects as `scrp_app`.
- **`scraper/gs1_fetch.py`** — sweeps `modification_timestamp` across all connected suppliers, paginates `get_chunks` until an empty page, upserts into `gs1.products`, records a watermark in `gs1.sync_runs` so the next run is incremental. `--full`, `--dry-run`, `--page-size`, `--max-pages` flags. Loads `.env` itself via python-dotenv.
- **Live data: 22,549 products across 77 suppliers.** Full sweep ran in 27s (46 pages × 500). Incremental runs since returned 3 and 1 rows respectively — the timestamp filter is honoured server-side.
- **Wired into the 03:00 cron** (`scraper/cron_main.py::run_gs1_catalog`), incremental mode, after the canonical-name step. Lazily imported and exception-wrapped so a GS1 failure logs but **never fails the supermarket scrape** — same treatment as the canonical step and `ping_supabase`.
- **`scripts/gs1_backfill_text.py`** — one-off backfill, imports `_clean_text` from `gs1_fetch` rather than reimplementing it so the two cannot drift. Dry-run by default.

Commits: `5a46ddf`, `ac2a778`, `7bc5729`, `3afed40`, `5d5369c`, `993bb52`.

**Three real bugs, all found by live testing rather than review — each invisible to the one before:**
1. **Nested response envelope.** The endpoint returns a *doubly* nested bare list `[[{row},...]]` — `payload[0]` is the row list, not `payload`. Killed the first dry run. Caught only because a diagnostic `sorted()` call raised on it; that line is now type-guarded so a shape surprise logs instead of aborting.
2. **Timezone-naive vs aware comparison.** The watermark round-trips through a `TIMESTAMPTZ` column and returns offset-aware; the API's timestamps parse naive. Comparing them raises `TypeError`. **Structurally impossible to hit on a first run** — with no stored watermark everything is naive — so it was guaranteed to appear only on run 2. Fixed with `_as_naive_local()`.
3. **`id` is not the stable key — `product_code` is.** GS1 reissues a changed product under a **brand-new `id`** while keeping its `product_code`. `ON CONFLICT (id)` therefore let the reissue through as a fresh INSERT, which then tripped the `product_code` UNIQUE constraint. Now `ON CONFLICT (product_code) DO UPDATE SET id = excluded.id, ...` — the row updates in place and adopts the new id. Verified: 3 reissued products adopted new ids, 0 rows left on the old ids, total unchanged.

**Also fixed:** the failure handler was running `UPDATE gs1.sync_runs` on an already-aborted transaction, so `InFailedSqlTransaction` **masked the real `IntegrityError`** and left a run stuck in `running`. It now logs the original exception *first*, then rolls back before recording the failure.

**Text normalization** — a supplier survey found the API returns HTML-escaped text (`Lord &amp; King`, `vegan&#039;s choice`) and pads values with stray spaces/newlines, so `מיה`, `מיה ` and `מיה\n` counted as three separate brands. `_clean_text()` now unescapes, collapses whitespace, trims, and maps blank → NULL, applied to `brandname` / `trade_item_description` / `group_name` (identifier columns deliberately excluded). Backfilled 5,498 historical rows: **distinct brands 1,582 → 1,351, i.e. 231 phantom duplicates collapsed**; entity/whitespace counts all to zero; totals unchanged at 22,549 / 77.

**Data inventory — what we actually hold.** Catalog *metadata only*: brand, trade item description, GTIN, GLN, category (`group_id`/`group_name`), status, and effective/discontinued/modification dates. **No images, no nutrition, no kosher certification.** The list response carries a `content` field but it is **empty in 100% of 200 sampled rows** — the richer per-product data lives behind the per-product detail endpoint. That is phase 2, and `full_content` JSONB + `full_content_fetched_at` + the partial index `idx_gs1_products_needs_full_content` already exist unused for it. Phase 1 never writes them, so a re-sweep cannot clobber phase-2 data.

**Phase-2 endpoints — ✅ RESOLVED AND DELIVERING DATA (2026-07-29).**

**CURRENT STATE — read this first:**
- **GS1 fixed the quota.** Rami (teum.co.il) confirmed the block was account-side and raised our pull allowance. Note the first retest ~1h after his email still returned identical 403s — **the change took some hours to propagate**, so a single failed retest after a support fix does not mean it didn't land.
- **Detail backfill: COMPLETE.** `scraper/gs1_fetch_detail.py` ran **11,492/11,492, 0 failures, ~2h06m** (7,595s, sustained 1.5–2.3 req/s). `gs1.products.full_content` is now populated on **11,496 / 11,496 targets — 100%**, ~59 MB of JSONB.
- **Field coverage:** Kashrut block **100%**, `media_assets` **100%**, ingredients **97%**, nutrition table **67%** (a third of products simply publish no panel — treat every field as optional).
- **Image pull: ✅ COMPLETE (2026-07-29 18:13).** `scraper/gs1_fetch_images.py`, resize to 800px / JPEG-80, **raw bytes never written to disk**. Final log line: `DONE — fetched=11,450 failed=46 skipped=0 in 11705s` (3h15m). 11,450 files on disk, **0.62 GB / 662 MB, avg 57.1 KB per image**; **24.92 GB of raw bytes were downloaded and never written**. Disk after: 13 GB free (55% used).
  - **The storage projection held — and beat itself.** Predicted ~0.83 GB, actual **0.62 GB (25% under)**. The resize-in-memory design is what made this feasible at all: raw would have been ~32 GB against a 30 GB volume, i.e. the naive approach could not have completed regardless of time.
  - **46 failures (0.4%), all benign and fully accounted for:** 39 × `UnidentifiedImageError` (bytes returned are not a decodable image) + 7 × `HTTP 404` ("file is missing on the server"). Both are upstream data defects, not our bugs — no retry is worthwhile.
  - **Zero 403s across the entire 3h15m run**, confirming Rami's quota fix is durable under sustained load, not just on spot checks.
  - Rate held at 1.0–1.1/s throughout, matching the "latency-bound, `--rps` never engages" note below.
- **Rate reality:** image calls are **latency-bound at ~1.1s each solo**, so `--rps` never engages and raising it does nothing. Under concurrent load with another job it degrades to ~3.7s — **don't run two long GS1 jobs at once.**
- **Gotcha:** the nightly GS1 sync fired *mid-backfill* and reissued row `id`s underneath it (our upsert keys on `product_code` and adopts new ids), leaving a 6-row gap. Harmless — the script skips already-populated rows, so a re-run closed it in 4s. Any long job keyed on `gs1.products.id` is exposed to this.

<details><summary><b>Historical: the 23-attempt investigation that preceded the fix (kept — still useful if this recurs)</b></summary>

> ⚠️ This block originally read "PROBED AND CONFIRMED WORKING (2026-07-28)". That was true of **one product** and wrongly generalised. The state below is what we saw *before* GS1 lifted the quota.
>
> **Tally: 23 distinct product_codes attempted, 1 success.** The single success was the original probe product `IL_7290000200002_7290013906892_1519196448768`, which returned 200 on every repeat, indefinitely. **Every other product returned `403 ["you have reached to your limit"]`** — a 34-byte body, byte-identical every time, regardless of supplier, product status, or parameters.
>
> **Six hypotheses ELIMINATED — do not re-test these:**
>
> | hypothesis | how it was ruled out |
> |---|---|
> | Credential / casing bug (the SU10A-1 class) | `gs1_fetch_detail.py` imports the *same* `_credentials()` as the working list script; `Authorization` headers are **byte-identical** (same SHA-256), both `Basic`, no whitespace, no casing variants present in env |
> | `hq` parameter value or presence | tested **all three** states — `?hq=1`, omitted, and `?hq=0` — identical 403 each time |
> | Per-supplier handshake / release | **17 failures vs 1 success within the same supplier** (`7290000200002`). If access were supplier-scoped they would behave alike |
> | Missing retailer GLN parameter | tried `&retailer_gln=`, `&gln=`, `&rgln=` with GLN `7292117800007` — all three ignored, identical 403 |
> | Rate limiting / daily quota | fails on the **first request of a fresh process**; no `X-RateLimit-*` or `Retry-After` headers exist at all; the 403 is origin-generated, not Cloudflare edge; **and it did not reset after 24h** (identical codes retested a day later → same 403, control still 200) |
> | Wrong `$Domain` / routing | **settled by DNS.** GS1's docs template these endpoints as `https://$Domain/…`; neither our GLN nor our account slug resolves in that pattern — **and the doc's own example host `fe.gs1-retailer.mk101.signature-it.com` does not resolve either**, so that naming scheme is retired, not parameterised. Our two working hosts (`retailer.` and `hq.gs1ildigital.org`) resolve to an **identical Cloudflare IP set**, so we are already reaching GS1's real infrastructure |
>
> **GS1 support (Rami, teum.co.il):** confirmed the cause is **account-side** and said they were *"increasing your pull allowance"*. Retested ~1 hour later against 3 fresh product_codes across 3 different suppliers — **still identical 403, no change whatsoever**. As of end of session this is **pending on GS1's end, with no ETA given.**
>
> **Outcome:** everything testable from our side was exhausted; the cause was account-side, exactly as the eliminations implied, and GS1 resolved it. `scraper/gs1_fetch_detail.py` (`b201804`) needed **no change at all** once entitlement landed — the code was correct throughout, the blocker was purely permissions. **If a `403 ["you have reached to your limit"]` ever returns, skip straight to GS1 support: all six hypotheses above were tested and eliminated, and the answer was on their side both times.**

</details>

The field shapes below came from genuine 200 responses and remain accurate. (This also corrects the SU10A-1 claim that the domain 404s — see the correction there.)

- **Detail:** `GET /external/product/{product_code}.json?hq=1` → 12.8 KB, JSON served as `text/html`, a **list of one** with keys `product_info` / `private_data` / `media_assets` / `multi_pack`. `product_info` holds **17 sections**, and everything phase 2 wanted is present:
  - `Kashrut` (9 fields) — Kosher_for_Passover, Kosher_Supervision_Type (בשרי/חלבי), Rabbinate, Board_of_Supervision, Sabbath_Observing_Plant, Sheviit_Orlah_Tevel. A full certification block with code pairs, not a flag.
  - `Product_Components_and_Instructions_General` — `Ingredient_Sequence_and_Name` (full ingredient string with percentages), `Allergen_Type_Code_and_Containment` + `..._May_Contain` (coded), `Diet_Information`.
  - `Nutritional_Values.table` — a structured panel (`numberOfRows: 9`), not free text.
  - Also useful: `Product_Dimensions.Price_Comparison_Content` (unit-price basis, e.g. `100 גרם`), `Case_or_Carton_Dimensions.Amount_of_Products_in_Package_or_Carton` (**the true source of the trailing `(N)` artifacts phase 1 strips**), storage/transport temperatures, `Produced_in_Israel`, `Parallel_Import`, `Private_Brand`.
  - `Internal_System_Fields.Product_Status` is a **code pair** (`מבוטל`/6306). The list endpoint exposes only the Hebrew string, so a stable status *code* exists only here.
- **Media:** `GET /external/product/{gtin}/files?media=all&default_image=1&hq=1` → **`{"file": "<base64>"}`**. **Not a URL — raw base64 JPEG**, 2.7 MB for a single image (EXIF: Canon 5D Mk III, "Yossi Mor Photography").
  - **Storage is the blocker, not access.** 2.7 MB × 22,549 ≈ **60 GB** if fetched wholesale. `product_image_url` cannot be filled from this without decoding, resizing and self-hosting the bytes.
  - `media=all` still returned a single `file` key while the detail response reports `media_assets: [3]`. Inspect `media_assets` first — it likely enumerates the assets and may allow requesting a specific or lower-resolution one.

**Operational gotchas worth keeping:**
- **The database is `xxl_super`, not `scrp`.** The repo, the server directory and the DB role are all `scrp`; the database is not. `psql -d scrp` fails.
- **`source .env` does not reach python3 subprocesses** — plain `KEY=value`, no `export`. Proven: `DATABASE_URL` set in the shell, unset in the child. Use `set -a; source .env; set +a`, or have the script load it (gs1_fetch does). Noted in CLAUDE.md § Server access.
- `sudo -u postgres` is **not** in the passwordless whitelist — migrations need an interactive `ssh -t`.
- **77 suppliers = 72 originally approved + 5 added directly by GS1**, confirmed against GS1's list. No supplier filtering is applied; the fetch pulls everything the account can see, so a drift in `count(DISTINCT gln)` means an authorization change, not a bug.
- `modification_timestamp` clusters hard: **17,391 of 22,549 rows (77%) fall in a 4-day window in Dec 2025**, and nothing predates 2025-12-28 — a bulk re-stamp/migration on GS1's side, not organic edits. July 2026 shows ~4.5× the Jan–Jun baseline.
- `product_status` is a closed set of three Hebrew values: `פעיל` (active, 15,226), `מבוטל` (cancelled, 7,320), `נבדק` (under review, 3). A third of the catalogue is cancelled — filter on `פעיל` for sellable products.

**Not yet done — next session:**
- **GTIN-matching against the `items` table** — the join path back to `items`/`item_code` per the 9d-11 scoping doc. Nothing has been matched yet; `gs1.products` currently sits entirely on its own.
- **Nothing is customer-facing.** No API endpoint, no UI, no enrichment of existing product data.
- **Phase 2:** per-product detail + media endpoints — the data is confirmed present and rich, but **bulk access is BLOCKED by an account-side limit** (23 product_codes attempted, 1 success). Pending with GS1 support. See the corrected block below before doing any further testing.
- The error-handler rollback path and the cron step inside a *real* 03:00 run are both still unexercised — the GS1 half is proven in isolation only.
- **⚠️ The images are fetched, not served — and nothing about that is automatic.** The 11,450 files sit in `~/gs1_images` on the VPS as loose files owned by `dude`. There is **no nginx location block, no static route, no CDN, no `product_image_url` column populated, and no API field exposing them**. Acquisition and serving are two separate pieces of work, and only the first is done. Serving them is its own task: decide a URL scheme, give nginx a web-root it can actually read (the files are outside every current root and `www-data` cannot read `~dude`), map GTIN → filename, and only then surface a field the frontend can consume.

> **Superseded by SU10A-3:** the first two "not yet done" bullets above are now done — GTIN matching shipped (`scraper/gs1_enrich_items.py`, 10,235 items stamped `name_source='gs1'`), and the enriched names are now genuinely customer-facing following the canonical_name fix.

---

### Session SU10A-3 (July 29, 2026) — Search relevance, canonical-name display bug, header logo

Non-GS1 work. All three items are backend or frontend fixes found while validating the GS1 enrichment.

**1. Header logo → portal (`d177f2a`, frontend deploy).**
`web/src/components/Header.tsx` wrapped the logo in a React Router `<Link to="/">`, which inside `AppShell` on super.xxl.co.il just re-rendered the current page. Replaced with a plain `<a href="https://xxl.co.il">`. Verified by bundle hash (`index-CWn-zrYr.js`, sha256 matched live vs local) rather than trusting the deploy script's "Done!" line.
- Note `AppShell` is *not* strictly super-only: App.tsx registers `<Route path="/*" element={<AppShell />} />` unconditionally and only `/` is hostname-switched, so `Header` also renders on e.g. `xxl.co.il/promos`. The link is sensible there too, but it isn't exclusively a super→portal jump.
- `scripts/deploy_frontend.ps1` now has an scp exit-code check — the old "prints Done! even when scp failed" gotcha is fixed. Still worth verifying by bundle hash.

**2. Search relevance overhaul (`65b700c`, backend + API restart).** Four distinct fixes in `db/query.py` / `api/routers/search.py`:
- **Tiered relevance ranking.** New `find_barcodes_with_relevance()` scores every match on the FIRST meaningful word: `0` item_name starts with it, `1` whole word elsewhere (`\y` regex boundary), `2` substring anywhere, `3` manufacturer_name only. Tier is now the PRIMARY sort key in `_build_result`, with the old ordering nested under it (multi-chain before single-chain, then cheapest).
- **Percentage tokens were silently dropped.** `_is_meaningful()` filtered `token.rstrip("%").isdigit()`, so "3%" was discarded and `חלב 3%` returned the same 2,247 results as `חלב`. Now only bare integers are filtered.
- **LIKE-escaping bug (why fix 2 alone wasn't enough).** `build_word_clause` built `%3%%` with no escaping, so the literal `%` acted as a wildcard and matched "300 גרם". Added `_like_escape()` + `ESCAPE '\'`. Result: `חלב 3%` now returns **41 codes, down from 2,247**.
- **Non-deterministic pagination.** `test_search_has_more_and_pagination` was **already failing on main** — `_PRICE_SQL` has no `ORDER BY` and the sort had no tie-break, so equal-priced items ordered arbitrarily and offset pages overlapped between requests. Added `item_code` as a final sort key. **Tests went 14 passed/1 failed → 15 passed.**
- **Gotcha found in manual verification:** tier 0 was first written as `item_name LIKE 'חלב%'`, and `%` matched the ה in **חלבה** — a halva snack ranked #1 for חלב. Fixed to `item_name ~ '^חלב\y'`; moved 89 items from tier 0 to tier 2. **A bare `LIKE 'word%'` is not "starts with that word" in Hebrew** — it's "starts with those letters".

**3. canonical_name display bug (`2fc012d`, backend + API restart) — the significant one.**
`_PRICE_SQL` selected `icn.item_name` (item_chain_names — one chain's raw scrape), and `group_by_product` assigned it straight to `canonical_name`. The chain chosen was **whichever key came first in the `best` dict** — arbitrary. So `items.item_name`, the column `canonical.py`'s nightly vote *and* the GS1 enrichment both write to, **was never displayed at all**.

Measured across **39,527 multi-chain items**:

| measure | count | share |
|---|---|---|
| canonical name matches NO chain name → never visible | 7,487 | 18.9% |
| >1 distinct chain name → displayed name is an arbitrary pick | 38,077 | 96.3% |

Split by source — this is why it went unnoticed for so long:

| `name_source` | multi-chain items | canonical never displayed |
|---|---|---|
| `chain` | 34,929 | 468 (**1.3%**) |
| `gs1` | 8,838 | 7,703 (**87.2%**) |

Majority-voted names usually *equal* one of the chain names by construction (the vote returns an existing string, it doesn't synthesise one), so the bug was nearly invisible until GS1 introduced names matching no chain string. **87% of the GS1 enrichment was landing correctly in the DB and never reaching a user.**

Fix: both `_PRICE_SQL` and `_PRICE_SQL_CITY` now also select `i.item_name AS canonical_item_name` (no new join — `items i` was already joined), and `group_by_product` + `group_by_store` read `r.get("canonical_item_name") or r["item_name"]` — chain-name fallback only when NULL. `names_per_chain` still reads `icn.item_name`, which is correct per-chain data.

Side effect worth knowing: **this also resolved the ranking-vs-display mismatch structurally.** Relevance tiering reads `items.item_name`; display now reads the same column, so no brand-stripping heuristic is needed. The goat-yogurt case (`7290012645297`) ranks tier 0 for "חלב" because its `items.item_name` is `"חלב הארץ, יוגורט עיזים…"` — the dairy *brand* — and now visibly displays that, so the placement reads as correct rather than arbitrary.

**Frontend impact checked, nothing changed.** Only `ProductCard.tsx:95` consumes `canonical_name`; its `<h3>` has no truncate class so longer names wrap. **`BasketResults.tsx`'s `truncate max-w-[130px]` is NOT affected** — it renders `item.item_name` from the basket model, a different field. Names grew from avg 20.7 → 25.1 chars (2,772 over 40 chars, 399 over 60, max 191). Nothing overflows; `line-clamp-2` on that `<h3>` is the minimal option if a ceiling is ever wanted.

**4. Bare numeric tokens were dropped from search (`8af63c4`, backend + API restart).** Direct follow-on from fix 2: removing the percentage filter exposed that `_is_meaningful()` still discarded every all-digit token, so a size in a query was silently thrown away and the search widened to *all* sizes. `במבה 80` returned all 72 Bamba products regardless of gram weight. `_is_meaningful()` is now just `len(token) >= 2` — length is the only remaining noise guard.

**Un-filtering alone was not enough, and this is the part worth remembering.** A bare number went through the same `LIKE '%n%'` as a word, which substring-matches *inside longer numbers*. On live data that made results wrong, not merely wide:

| query | word alone | + numeric via LIKE | false matches |
|---|---|---|---|
| `במבה 80` | 72 | 7 | 1 (`…פסח806`) |
| `חלב 80` | 2,267 | 60 | **35 — 58%**, all 180/280/380 g |

Bare numbers now match on a **digit-run boundary**, `(^|[^0-9])80([^0-9]|$)`, via new `_digit_run_pattern()`; non-numeric tokens keep the existing `LIKE`/`ESCAPE` path untouched. **Anchoring on non-digits rather than Postgres `\y` is deliberate** — `\y` treats `80גרם` as one word and would silently drop real matches, and the catalog genuinely writes quantities glued to the unit (`סוכריות ריבת חלב ללא סוכר 80גרם`). This is the same lesson as fix 2's `LIKE 'חלב%'` gotcha in a new guise: **the obvious boundary primitive is wrong for this data both times.**

Verified live: `במבה 80` → **6 rows, all 80 g** (from 69); `חלב 80` → 25 with all 35 false entries gone; `חלב 3%` still 43 rows, tier-0 ordering intact. **15 passed.** Performance-neutral — no trigram index exists, so the `LIKE` was already a full seq scan over 139K items.

**Known limitation, deliberately not fixed:** relevance *tiering* still uses `\y` when the first token is numeric (e.g. `q="80 גרם"`), so `80גרם` lands in a lower tier. Affects ordering only, never which rows match.

**Deploy pattern for backend changes:** `git pull` on the server + `sudo /usr/local/bin/xxl-restart.sh scrp-api` (passwordless whitelist). **No frontend deploy** — `deploy_frontend.ps1` only ships `web/dist`. Items 2, 3 and 4 were backend-only; only item 1 needed the frontend deploy.

---

### Session close — 2026-07-29

**GS1 image pull finished at 18:13:** `fetched=11,450 failed=46 skipped=0 in 11705s`. 0.62 GB written against an ~0.83 GB projection — **the storage projection held.** Full detail in the SU10A-2 entry above.

**What today actually delivered:** GS1 phase-2 detail backfill at 100% (11,496/11,496), the image pull complete, and four search/display fixes shipped to production.

**⚠️ What is NOT done — these are real future tasks, and none of them happen on their own:**

1. **Images are not served anywhere.** 11,450 JPEGs sit in `~/gs1_images` on the VPS as loose files owned by `dude`. No nginx location, no web-root, no URL scheme, no `product_image_url` populated, no API field. `www-data` cannot even read `~dude`, so this is not a config tweak away from working — it needs a deliberate serving design.
2. **None of the phase-2 product data is in the UI.** The nutrition tables, kosher/Kashrut certification blocks, ingredient strings and allergen codes pulled today all live in `gs1.products.full_content` as JSONB and **stop there**. No API endpoint reads them, no model exposes them, no component renders them. Fetching the data and surfacing it are separate pieces of work and only the fetch is done.

Both items are frequently assumed to follow automatically from the backfill. **They do not.** The only GS1 data currently reaching a user is the enriched *product name*, via the `canonical_name` fix in item 3 above — nothing else.

> **Superseded by SU10A-4 (next entry):** both "NOT done" items above shipped the following day — images are served via `GET /product/{item_code}/image` and the phase-2 data via `GET /product/{item_code}/details`, both surfaced in the product detail modal.

---

### Session SU10A-4 (July 30, 2026) — GS1 product detail modal shipped + dropdown search + deploy process fixes

**GS1 phase-2 data now customer-facing — closes the two items flagged NOT done at the end of SU10A-3.**

Two new backend endpoints (`api/routers/product.py`):
- `GET /product/{item_code}/details` — 200 with `has_gs1_data: true` + full payload (kashrut, nutrition table, ingredients, allergens, brand, gs1_name) when a GTIN match exists; 200 with `has_gs1_data: false` + null fields when the item_code is real but has no GS1 match (the common case, ~91% of products); 404 only for a genuinely unknown item_code; 400 for a malformed barcode.
- `GET /product/{item_code}/image` — serves the resized JPEGs from `~/gs1_images` (filename = GTIN = item_code, no DB hit, digits-only barcode check prevents path traversal). 200 with long-lived cache headers, 404 when absent.

Frontend: `ProductDetailModal.tsx` — bottom sheet on mobile / centered card on desktop, single `<button>` combining the "מידע נוסף" label and + icon (deliberately one control, not two, for accessibility — two elements firing the same action is a bad a11y pattern, not just visual redundancy). Sections self-hide when empty. A failed `/details` call silently falls back to the no-data view rather than erroring, since GS1 enrichment is supplementary. Mobile-viewport verification was explicitly deprioritized — a native iOS/Android app is planned, so the mobile browser experience is not a priority surface.

**Deploy incident, root-caused and fixed — worth reading if a future deploy looks broken:**
Pushing to GitHub does not update the server. `git push` only updates the remote; restarting `scrp-api` after a push without an explicit `git pull` on the server just relaunches the *old* code. This shipped a broken state for several hours (endpoints 404ing, frontend gracefully falling back to "no data") before being caught. Fix now documented in CLAUDE.md's new "Deploy backend" section — always `git pull origin main` on the server before restarting.

**Same commit (`c3833a0`) also swept in two unrelated stray files via `git add -A`:**
1. `data/city_canonical_review.csv` — a completely different 9-column/1,078-row version from the Windows dev machine collided with the server's own independent ~1,078-row uncommitted local edits to the same file, blocking the pull. Resolved by reverting just that file back to its exact pre-`c3833a0` git content (`3553e03`) — this made the file a no-op in the incoming diff, so the pull went through without touching the server's local edits at all. **The server's uncommitted local CSV edits are still sitting there, untouched, exactly as before** — not lost, not committed, still a single-disk-failure risk, still worth a dedicated city-data session to review and commit properly.
2. A stray duplicate `handoff_super.md` at repo root (1,274 lines, diverged from the real `docs/super/handoff_super.md`) — removed (`a6e0e9d`).

**City/chain dropdown search (`41cd14f`, frontend-only deploy).** Added a search box to the shared `MultiSelect` component in `Filters.tsx` — covers both the city and chain filters. Autofocused input, case-insensitive substring filter, "no results" state, select-all unions the filtered set with the existing selection rather than replacing it. Verified against the live 146-city catalog on production.

**Flagged for future care, not urgent:** search appears to be missing fresh produce / meat / fish / chicken categories — may be a PriceFull data gap (these chains may not publish loose/weighted goods the same way as packaged items) or a search/categorization issue. Not investigated this session; worth a dedicated look.

**Still the top explicit priority, unchanged:** the promo pipeline remains CRITICALLY BROKEN (Victory alone has 60K+ corrupt rows) and needs a dedicated audit-and-rebuild session — do not attempt incremental fixes.

> **Superseded by SU10A-5:** that rebuild happened and the premise did not survive it. The rows were never corrupt — a UNIQUE constraint makes duplicates impossible, and Victory's data is among the cleanest we hold. The promo pipeline is REBUILT and RESOLVED: all 14 chains populated, discounts computed at read time. See SU10A-5.

**Session naming note:** this session continues the SU10A-* lineage (SU10A-1 → SU10A-4) rather than switching to the CLAUDE.md table's stated SUXX-a format — a deliberate decision made this session, not an oversight. Future sessions should keep using SU10A-N.

---

### Session 9d-9 (June 5, 2026) — Delta Files + Promo Pipeline + HaziHinam + Missing Stores

#### Final state
- 14 chains, 812 stores, 4,925,598 prices
- All 14 chains updated today (5.6.2026) — first full clean run
- Cron runtime: 7615s today (seeding run) — expected ~15-20 min next week with delta
- Errors: none on manual run

#### What was completed
- Delta Price files for 8 chains (Shufersal + 6 Cerberus + HaziHinam)
- Per-store ThreadPoolExecutor parallelism (STORE_WORKERS=4)
- PriceFull fallback when no delta found for a store
- Promo pipeline: promos table, parse_promo_file, bulk_insert_promos, build_promo_index for Shufersal/Cerberus/HaziHinam
- HaziHinam scraper (11 stores, seeded from store 103)
- Missing stores: Rami Levy +72, Yochananof +35, Keshet +12, Osher Ad +11, Carrefour +133, HaziHinam +1
- Connection pool: 20+10, chain workers: 4
- SQLite fallback removed — fail fast on missing DATABASE_URL
- docs/portals.md and docs/chain_registry.md created
- chains table populated for all 14 chains

#### Next session (9d-10) priorities
1. API endpoint for promos + frontend highlighting (≥10% discount or 2-for-1)
2. Store address/branch name in search results (from StoresFull XMLs)
3. Measure Sunday cron runtime — if <20 min, consider STORE_WORKERS=8
4. Fix DATABASE_URL export in systemd service (Environment= directive)
5. Victory + BinaProjects delta (portals were down Friday)
6. Supabase keep-alive: sudo systemctl enable supabase-keepalive.timer && sudo systemctl start supabase-keepalive.timer

---

### Session 9d-9 (June 4-5, 2026) — Delta Price Files + Per-Store Parallelism + Hazi Hinam + Missing Stores

#### Performance
| Chain | Before | After | Speedup |
|---|---|---|---|
| Shufersal | 4436s (74 min) | 544s (9 min) | 8× |
| Tiv Taam | 6913s (115 min) | 93s (1.5 min) | 74× |
| Rami Levy | ~600s | ~132s | ~4.5× |

#### Delta Price file architecture
- Daily cron now uses Price (delta) files instead of PriceFull for 8 chains
- DELTA_CHAINS: Shufersal, Rami Levy, Osher Ad, Yochananof, Keshet, Fresh Market, Super Yuda, Hazi Hinam
- Excluded from delta: Tiv Taam (no delta files published), Carrefour (portal down), Victory/King Store/Shefa/Shuk Hayir (non-Cerberus, needs build_price_index)
- PriceFull remains available via --full flag in run_one.py for seeding new stores
- Generator exhaustion bug fixed in shufersal.py (items = list(items))

#### Per-store parallelism
- ThreadPoolExecutor(max_workers=STORE_WORKERS=4) added to base.py and shufersal.py
- Each worker thread owns its own DB connection (connect()/close() inside worker)
- fetch_runs row inserted upfront with status='running'; workers write fetch_store_runs per-store
- OOM incident during testing — root cause was two parallel Shufersal runs (manual + cron), not a code bug

#### חצי חינם scraper (new chain — priority 3)
- Chain ID: 7290700100008, 11 physical stores (201-217, store 103=online excluded)
- Portal: shop.hazi-hinam.co.il/Prices — public Azure Blob, no auth
- PriceFull only published for store 103 (online) — physical stores get Price delta only
- Seeding strategy: seed_hazihinam.py copies store 103 PriceFull to all 11 physical stores (92,103 prices)
- Daily delta: 11/11 stores, 4 seconds, confirmed working
- docs/portals.md created — portal credentials and delta status for all chains

#### Missing stores expansion (priority 2)
| Chain | Before | After | Added |
|---|---|---|---|
| Rami Levy | 26 | 98 | +72 |
| Yochananof | 15 | 50 | +35 |
| Keshet | 10 | 22 | +12 |
| Osher Ad | 12 | 23 | +11 |
| Hazi Hinam | 11 | 12 | +1 |

- All new stores seeded with PriceFull via run_one --full before delta takeover
- Yochananof: only 3/50 files loaded in seed run — needs investigation
- Osher Ad: 0 files in seed run — likely delta-only portal, needs investigation

#### Commits this session
- 82c190b: delta Price file support for Shufersal
- 3b19a25: fix generator exhaustion (items = list(items))
- ab4de5c: per-store ThreadPoolExecutor parallelism
- 277dc74: delta for all Cerberus chains + docs/portals.md
- d8bb4aa: seed_hazihinam.py
- 84abe57: run_one delta flag
- 7aaa986: run_one --full flag
- 533e9e4: missing stores for 5 chains

---

| Session | What | Status |
|---|---|---|
| 1–6 | Project skeleton, SQLite schema, XML parser, Shufersal scraper, search CLI, Rami Levy + Osher Ad scrapers, basic API + UI | ✅ |
| 7a | Railway backend + Postgres migration | ✅ |
| 7b | Frontend deploy + custom domains + DNS | ✅ |
| 8a | Victory/Yochananof/Keshet scrapers + SQLAlchemy port + snapshot mode + cron | ✅ |
| 8b | Canonical naming via majority/weighted voting + search filtering | ✅ |
| 8c | OpenFoodFacts enrichment (Hebrew names, images) | ✅ Code ready, partial production data |
| 8d | (skipped/deferred — was about Shufersal image scraping) | — |
| 9a | Basket feature (UI + API) + Hostinger deployment fix + 25-item limit toast | ✅ |
| 8L | Brand identity + animated XXL logo + custom favicon | ✅ |
| 9b | User authentication via Supabase + saved baskets | ✅ Email/pass + saved baskets in production. Google OAuth deferred. |
| 9c | Mini-9c + Favorites + Recent Searches | ✅ 150-item logged-in cap, server-side favorites with heart icon, localStorage recent searches dropdown, cheapest-indicator visual fix |
| 9d-1 | City expansion Phase 1 + Carrefour scraper + verification system | ✅ Carrefour scraper + `publishprice.py` base class shipped. 5 new cities added. PriceFull-verification gate (`active_stores.yaml`) shipped. 58 verified / 14 excluded. Cron-command persistence bug found and fixed (Procfile now authoritative). Surfaced: geo-blocking on 2 chains, ~2min/store scrape bottleneck, Shufersal sub-chain heterogeneity. |
| **9f** | **XXL Portal Page — live on xxl.co.il** | ✅ Portal landing live at https://xxl.co.il with 3 vertical tiles, AI search bar (mocked router), 2 בקרוב sub-pages, hostname-based routing in React. Hebrew defaults fixed. DNS + parked domain + SSL + clean root URL all working. |
| **9f-followup** | **Portal polish: SEO, OG, email signup backend, GA4 + cookie banner** | ✅ SEO/OG meta tags hostname-aware. Email signup writes to Supabase portal_email_signups table. GA4 wired (pending Eltzur measurement ID swap). Minimal Hebrew cookie banner with X-dismiss-as-consent. |
| **9g** | **Scraper performance + full Railway → Kamatera migration** | ✅ Bulk inserts (9g-1). Scraper + Postgres migrated to Kamatera (9g Phases 2-6). FastAPI web service migrated to Kamatera with nginx + Let's Encrypt (9g Phase 7). Railway fully decommissioned. Cron 3m31s, 7 chains, all geo-blocks resolved. |
| **9k** | Rami Levy split-store reconciliation | ✅ 14 Rami Levy stores existed as duplicate stores rows (sub_chain_id='1' legacy + '001' canonical), prices split. Merged onto '001', 89,298 duplicate price rows removed, 1 stale Shufersal ONLINE duplicate cleaned. No scraper code change needed (_pad_store_id from 9j-followup already prevents recurrence). |
| **City-data fix** | store→city correction | ✅ Victory wrote full store name into city column; Yochananof name-guessing picked streets. 17 stores corrected in DB (9 via override map, 8 Yafo variants). Added STORE_CITY_OVERRIDES in city_names.py + 'תל אביב יפו'/'יפו' normalization. Deployed. |
| **9d-3** | Shufersal per-store fetch + Tiv Taam onboarding | ✅ Shufersal global page-scan eliminated; per-store fetch (1 req/store, same shape as all other chains). TivTaam Cerberus scraper shipped: 46/46 stores verified, 0 city NULLs, wired as 8th chain in cron. CITY_CODES: 12 new MOI codes + 7 spelling/name overrides. King Store / Paz brands (freshmarket) / Dor Alon deferred — see 9d-3 session notes. |
| **9d-4** | King Store (bina-projects) + Supabase keep-alive fix | ✅ King Store live as 9th chain (chain_id 7290058108879): 28 publishing stores, 148,016 prices, Arab-sector cities. BinaProjectsScraper reusable base class (ZIP-not-gzip fix, 3-endpoint JSON portal). Supabase ping fixed to hit real Postgres via /rest/v1/. scripts/run_one.py added. |
| 9d-5 | 2026-05-28 | Shefa Birkat Hashem + Shuk Hayir (chains 10 & 11) onboarded via BinaProjectsScraper base class. 50 stores added, ~141K items in production Postgres. |
| **9d-6** | CITY_VARIANTS cleanup + Shufersal full sweep + 4 new chains + Kamatera frontend migration | ✅ Shufersal 25→320 stores (95 BE excluded). Dor Alon/AM:PM, Paz/Alonit, Fresh Market, Super Yuda added. Registry: 15 chains. Frontend migrated to Kamatera nginx. |
| **9d-7** | StoresFull XML ingestion + cron fixes | ✅ 244 city_norm rows updated from StoresFull XMLs. systemd timeout→infinity + 4G swap (OOM fix). Cron: 429 stores, 2.45M prices, 11 chains. Decision: switch to delta (Price) files for daily scraping. |
| **9d-8** | city_canonical rebuild + parallel chains + Shufersal 403 fix | ✅ CBS 2024 city_canonical: 1057 stores, 0 NULLs. Paz/Dor Alon removed (422 stores, 887K prices deleted). City dropdown 0.13s (was 3.7s). Chain-level ThreadPoolExecutor(max_workers=6). Shufersal lazy per-store URL fetch (403 fix). |
| **9d-9** | Delta Price files + per-store parallelism + Hazi Hinam + missing stores | ✅ Delta for 8 chains (Shufersal + 6 Cerberus + Hazi Hinam). STORE_WORKERS=4 — Shufersal 4436s→544s (8×), Tiv Taam 6913s→93s (74×). HaziHinam scraper + seed script. +131 missing stores (Rami Levy +72, Yochananof +35, Keshet +12, Osher Ad +11, Hazi Hinam +1). docs/portals.md. run_one.py --full flag. |
| **9d-10** | Store seeding fixes + search performance + geolocation + promo failure | ✅ Carrefour 59→148 stores (regex+padding fix). Victory rewritten to laibcatalog REST API (17→69 stores). Shufersal stores 413+844 added. Search 14s→0.28s (covering index + nestloop off + store_fk pre-fetch). IP geolocation city auto-detect. API warmup /health ping. docs/xxl-stack.md created. ❌ Promo pipeline CRITICALLY BROKEN (60K+ corrupt rows) — marked failed, needs full audit and rebuild. **[Superseded by SU10A-5: the rows were not corrupt; pipeline rebuilt, all 14 chains live.]** |

---

## Potential Data Sources

External data sources we're evaluating for catalog enrichment. Each entry tracks status, key questions, and decision gates. **Single source of truth — do not split into separate files.**

### GS1 Israel — Digital Catalog of Items (added May 14, 2026)

**What it is:** GS1 IL's digital catalog — barcode-keyed (GTIN) product master data. GS1 is the global NGO that owns the barcode standard. The Israeli chapter operates the local catalog at https://www.gs1il.org/what-is-the-digital-catalog-of-items/

**Fields offered (per their marketing page):**
- Barcode (GTIN) — canonical product ID
- Full product name + description (canonical, brand-owner authored)
- Images — including 360° and marketing imagery
- Nutritional info
- Kashrut certifications
- Logistics data (pack sizes, weights)
- Brand / marketing metadata

**Why high-priority:** Closes the three gaps the OS scraper research (May 14) flagged — canonical names, brands, images — from a single authoritative source. Bonus fields (kashrut, nutrition, 360° images) unlock future verticals like dietary filtering, allergen flagging, and richer product detail pages.

**Architecture fit:** Enrichment layer joined to existing scraper output via barcode (GTIN). NOT a replacement for the gov.il scraper — gov.il still needed for prices. Clean add-on, not a rewrite.

**Status:** Eltzur registered via gs1il.org website on May 14, 2026. Awaiting contact from GS1 IL with details.

**Open questions for GS1 IL (in priority order, ask in first reply):**
1. Is a price-comparison / consumer-info platform eligible as a data consumer, or is read access restricted to retailers/manufacturers?
2. Pricing structure for read-only API or data feed access for our use case?
3. API specification — REST / bulk file download / GraphQL? Rate limits? Update frequency?
4. Coverage — what % of Israeli grocery SKUs are currently in the catalog?
5. Image licensing — can we display catalog images on a consumer-facing site at no extra cost, or is there a per-display / per-API-call fee?
6. Data freshness SLA — how often do brand owners update their listings?

**Decision gates:**
- 🟢 GREEN: Platform-eligible access, ≤₪3k/month, REST API or bulk feed, ≥70% SKU coverage → prioritize integration immediately after 9g
- 🟡 YELLOW: Eligible but pricier (₪3-10k/month) → defer until pre-revenue funding lands or revenue covers it
- 🔴 RED: Retailer-only access OR ≥₪10k/month → file under "revisit at scale"

**Important caveats (don't assume too much from marketing page):**
- GS1 is non-profit but NOT free. Pricing varies wildly by country and tier — could be hundreds or tens of thousands of shekels annually. Unknown until they reply.
- Catalog only covers products whose brand owners have opted in. Israeli participation rate unknown.
- Doesn't replace gov.il for prices — GS1 carries product master data, not commercial pricing.

**Follow-up cadence:** If no reply from GS1 IL within 5 business days (target: May 21, 2026), Eltzur sends a polite follow-up via their contact form or phone (03-5198714).

**Relationship to other sources:** GS1 and StoreNext are PARALLEL candidates, not mutually exclusive. GS1 is brand-owner-sourced (manufacturer-uploaded); StoreNext is retailer-sourced. They may complement each other — GS1 fills the canonical-name + image gap, StoreNext could fill chain-specific pricing/promo metadata. Pursue both threads in parallel.

---

### StoreNext (status: REJECTED — pricing prohibitive, May 17, 2026)

**Status:** Outreach completed May 2026. StoreNext quoted **NIS 30,000 (~$8,000 USD) for a one-time Excel export** of their catalog data. Pricing is approximately 4 years of scrp's total infrastructure budget for a static, single delivery (not even an ongoing API or feed). Hard pass at current stage.

**What we'd have gotten:** Branch lists for all 7 chains with sub-format classification, potentially product catalog data. Free CSV branch lists at `storenext.co.il/תמיכה-ושירות/` remain accessible — those are still useful for the 9e Registry idea if we revisit it (see decision below).

**Why rejected:**
- Price is one-time, not subscription — no obvious "grow into it" tier
- Single Excel export means data goes stale; not an ongoing relationship
- ROI doesn't work pre-revenue. Even if StoreNext data unlocked premium tier conversions, NIS 30K is years of recouping at hobby pricing
- GS1 IL (pending reply) is the better-shaped data source — barcode-keyed canonical product master data with images, kashrut, nutrition. Different layer than StoreNext's chain-store-registry focus
- The actual gaps we wanted to close (images, brands, canonical names) are addressed by GS1, not StoreNext

**Future:** Revisit only if (a) GS1 path doesn't pan out AND (b) scrp has revenue or funding to absorb the cost. Re-engage StoreNext at scale (5K+ MAU, paying premium tier exists) when the value calculation flips.

**Free StoreNext data still usable:** Branch CSVs at `storenext.co.il/תמיכה-ושירות/` are free and can power the 9e Registry concept independently of the paid catalog. Re-scoped 9e (see Pending Sessions) reflects this.

---

### OpenFoodFacts (status: abandoned)

Tried during earlier catalog enrichment exploration. Abandoned due to poor Israeli barcode coverage (most IL grocery SKUs absent from the global OFF database). **Do not revisit.**

---

## 🧭 Pending Sessions

| Session | What | Notes |
|---|---|---|
| **9m** | Cron hardening + post-holiday cleanup | ✅ Carrefour retry/backoff (9m partial, prior). This session: Shufersal parse_filename store_id padding bug FOUND & FIXED (commit 63ec27e — both return paths now .zfill(3); was returning unpadded '2'/'5'/'21' so PriceFull index never matched padded DB targets). City dropdowns sorted alphabetically (Hebrew localeCompare) instead of by chain count. Stale Railway DATABASE_URL removed from local .env. .gitattributes added (*.py eol=lf) + shufersal.py renormalized (kills phantom 261-line CRLF diffs). Carrefour store 1167 split-pair resolved. Shufersal page-cache verification DEFERRED to next session (holiday — no fresh PriceFull files, inconclusive). |
| **9m-followup** | Shufersal verification + Carrefour padding fix | ✅ Shufersal padding fix (63ec27e) verified — metadata returns 3-digit store IDs. Carrefour PriceFull lookup padding bug found & fixed: base.py now normalizes target store_id via _pad_store_id before index lookup (commit 0812bdc) — stores 60/81 were silently skipped because active_stores.yaml has unpadded IDs ("60") while the index keys are zero-padded ("060"). Store 6 confirmed a genuine upstream Carrefour publishing gap, not a code bug. Hostinger frontend deploy: alphabetical city sort live (85ee335). |
| **9n** | 3-chain diagnostic + cron timing fix + FreshnessStrip deploy | ✅ Root cause of Victory/Osher Ad/Carrefour daily zero-loads identified: timing race — cron at 03:00 IDT (midnight UTC) fires before portals publish. Portals confirmed to publish 02:09–05:00 UTC consistently over 6+ days. Cron timer moved to 10:00 IDT (07:00 UTC) via `sed` on Kamatera `/etc/systemd/system/scrp-cron.timer`. Catch-up run succeeded all 7 chains. FreshnessStrip downward-expand code confirmed correct in web/ source (was never deployed). web/deploy.zip rebuilt — awaiting Hostinger upload. Column-misalignment report in 9n table was RTL terminal rendering artifact; DB data confirmed correct. |
| **9f-followup** | ~~Portal polish~~ | ✅ Done May 14, 2026. See session detail below. |
| **9h** | **Claude Haiku integration for portal search** | Replace `web/src/utils/portalSearchRouter.ts` mock classifier with real Claude Haiku API call. Function signature already designed for one-line swap. Budget: ~$5/mo at 1K daily queries. |
| **9i** | Contact form on xxl.co.il | Real form with Supabase backend + spam protection + email notifications. Currently footer has mailto link only. |
| **Server hardening** | sudo NOPASSWD for dude, disable root SSH, HSTS header, compress OG images (~5.6MB each) | Small cleanups, batch into one ~30 min session. |
| **9g-2** (deferred) | **Parallel chain execution** | Skipped after 9g-1 results. Sequential cron now 3m31s; parallelism would save ~2.8 min. Low ROI until something specific unblocks it. Revisit when full cron pressure returns. |
| 9e (rescoped) | StoreNext FREE branch CSV ingestion | Original 9e premise (paid product catalog) dead — StoreNext paid tier rejected (NIS 30K one-time, May 2026). Free CSV branch lists at `storenext.co.il/תמיכה-ושירות/` remain usable. Rescoped to: ingest free branch CSVs only into `chain_stores_registry` table with sub-format classification (Sheli/Deal/Express/Yesh/Universe/BE for Shufersal; similar for others). Refactor Phase B selection to be format-aware. Solves Shufersal sub-chain heterogeneity systematically. No longer urgent since verification gate (9d-1) already prevents silent failures — quality-of-life, not blocker. |
| 9d-2 | City expansion Phase 2 | Remaining 12 cities >100K pop (Petah Tikva, Netanya, Holon, Ramat Gan, Ashkelon, Rehovot, Bat Yam, Beit Shemesh, Kfar Saba, Herzliya, Modi'in). Target ~216 stores total. **Requires 9g first** — running 216-store cron at current 1.5min/store = 5+ hours. |
| 9d-4 | City expansion Phase 3 | 50K+ cities (~25-30 more). Target ~540 stores. |
| **stores table data hygiene** | **Add format guard to `sub_chain_id` / `store_id`** | Rami Levy split (was `sub='1'` vs `'001'`) resolved in 9k; Carrefour `store_id` padding resolved in 9j-followup. base.py lookup now routes through `_pad_store_id` (9m-followup, commit 0812bdc) — a drifted yaml store_id resolves correctly instead of silently failing. A CHECK constraint on the stores table is now optional/nice-to-have, no longer urgent. |
| Promotions + price history | Parse Promo XML files, build history charts | Sample Promo XML files captured in 9d-1 for future analysis. Requires sufficient daily snapshots first. |
| Google OAuth | Wire up deferred-from-9b option | Requires Google Cloud Console OAuth client setup |
| Investigate disappearing tables | Risk hygiene | Deferred pending future AWS/GCP migration (decided in 9c planning) |
| **Search Quality** | Hebrew search precision fixes | Word-boundary matching, kosher-marker filtering ("חלבי"/"פרווה"/"בשרי" leaking into "חלב"/"בשר" searches — example: jelly appearing under "חלב" because it's labeled "חלבי"). Stretch: Hebrew stemming. Defer until after StoreNext data is in hand (may solve upstream via better categorization). |
| **OS scraper research** | ~~Review OpenIsraeliSupermarkets repos + Kaggle dataset~~ | ✅ Done May 14, 2026. Writeup at docs/research/os_scraper_2026_05_14.md. Key findings: MIT-licensed (not GPL/AGPL as feared), geo-block is industry-wide (confirms 9g VPS plan), Kaggle dataset NOT a Carrefour/Victory stopgap, no new sources for images/categories/brands (StoreNext still the path). |

---

## 📌 Open Items — Next Session (9d-10)

- **Confirm full cron run** — check 10:00 IDT tomorrow. Expected <30 min with per-store parallelism (STORE_WORKERS=4) + chain-level parallelism (max_workers=6). First run with delta for 8 chains.
- **Supabase keep-alive** — timer files deployed to `deploy/systemd/`, still needs enabling on server:
  ```bash
  sudo systemctl daemon-reload && sudo systemctl enable supabase-keepalive.timer && sudo systemctl start supabase-keepalive.timer
  ```
- **Seed Hazi Hinam** — run `python3 -m scripts.seed_hazihinam` on server before next cron (seeds physical stores 201-217 from store 103 PriceFull so delta can apply incremental updates).
- **Missing stores — Victory + Carrefour** — Victory: 51 stores missing from yaml vs StoresFull XML. Carrefour: 125 stores missing (portal was down June 4, check when back up).
- **Delta for non-Cerberus chains** — Victory (REST API), King Store / Shefa / Shuk Hayir (Bina Projects) need `build_price_index` per portal type.
- **9d-2 city expansion — cleared to start.** No remaining blockers. Needs a fresh PriceFull verification run. Begin in a fresh chat. First step: reconcile the handoff's city list against the live DB before picking new cities (the 58→216 math assumed a 7-city baseline that was already wrong).

---

## ⚠️ Watch Items (low priority, but don't forget)

- **RTL terminal display is cosmetic only.** Hebrew store names render
  reversed in psql/SSH terminal output (e.g. 'קרפור' shows backwards). The
  data in the DB is correct — verified repeatedly. Do not "fix" reversed-looking
  Hebrew in SQL strings; copy Hebrew values from the actual DB query output,
  not from terminal-rendered text.
- **Supabase Data API default change** (email received May 12, 2026): starting May 30 for new projects, October 30 for existing projects, new tables in `public` schema won't be exposed via supabase-js / REST / GraphQL by default. **Existing tables keep their grants**, so super.xxl.co.il is unaffected for current code. For NEW tables created after Oct 30, 2026, must run explicit GRANT statements if they need to be reachable from the frontend. Pattern: `GRANT SELECT, INSERT, UPDATE, DELETE ON public.your_table TO authenticated;` + RLS policy. Backend-only tables (FastAPI direct connection) are unaffected. Review Security Advisor in Supabase dashboard.
- **Carrefour 0-items issue (May 18, 2026)** — ✅ Resolved May 19. Transient upstream gap. Cron picked up 9/9 stores (32,060 items) next day.
- **Shufersal `prices.shufersal.co.il` portal outage (May 19, 2026)** — Server-side outage from ~03:00 IDT through ~16:00 IDT. Confirmed not on our end (timed out from laptop + Kamatera + multiple browsers). Recovered late afternoon — 16:35 IDT cron run got 1/1 files, 4,939 items. Total chain still slow (~28 min in Shufersal phase) due to page-scan bottleneck — accelerates the "Shufersal page-scan cache" pending session priority.

---

## 🔑 Key Architectural Decisions

- **Full Kamatera consolidation (May 18, 2026)** — All production infra on Kamatera Tel Aviv VPS ($17/mo after Jun 17 free trial expires): Postgres + scraper cron + FastAPI behind nginx + Let's Encrypt. Railway fully decommissioned May 18. Single host, single bill, no cross-host network latency, no geo-block issues.
- **SQLAlchemy everywhere** — scrapers are DB-agnostic.
- **Snapshot pricing only** — not yet tracking history (deferred to 9d).
- **Phased city expansion strategy** — currently 58 stores across 14 cities (verified May 24, 2026 — see live city dropdown). Sessions 9d-2+ expand to all 100K+ cities (~216 stores). Sessions 11+ expand to 50K+ cities (~540 stores). Full coverage requires AWS/GCP migration when Railway hits limits.
- **Daily cron at 10am Israel time (7am UTC)** (changed from 3am in session 9n — portals publish 02:09–05:00 UTC; 10:00 IDT clears the window).
- **Canonical names via weighted token voting** — ~93% stability across runs, ~7% updated per fresh canonical run.
- **Skipped Hazi-Hinam scraper** — HTML-scraping is too fragile vs Cerberus JSON APIs.
- **Brand color: emerald-600 (#059669)** — used for primary CTAs, basket-limit toast.
- **Freemium model REDEFINED (session 9a → confirmed 9c)** — Free tier is the honeypot: search, view prices, basket comparison, save baskets, favorites, recent searches — ALL free, ALL unrestricted. Paid tier benefits will be: ordering through us (12+ months out, requires chain partnerships), exclusive deals, price-drop email alerts. The original "freemium = limit free users to 25 basket items" framing was retired in 9a and codified in 9c — only logged-out users see the 25-item cap (as a signup nudge); logged-in users get a generous 150 (effectively unlimited for human use).
- **Verification-before-scrape pattern (9d-1)** — `scheduled_stores.yaml` is the intent/wish-list, `active_stores.yaml` is the actually-scraped list, gated by per-portal `verify_publishes_pricefull()` check. Prevents silent scrape failures from sub-chain heterogeneity (Shufersal Sheli format, warehouse nodes, etc.). Verification reports go in `db/verification_report_9d1.md`.
- **Procfile is authoritative for Railway commands (9d-1)** — was Railway-UI-only before, which caused scraper-cron to silently revert to `fetch_off` on scheduled runs while manual triggers worked. Procfile now defines both `web:` (gunicorn API) and `cron:` (scraper price scrape). Survives service recreation.
- **Carrefour Israel under Global Retail C.I.** — chain_id `7290055700007` publishes Carrefour + Mega + Yenot Bitan stores combined. We display as "קרפור" but accept all sub-brands. Bnei Brak has zero Carrefour/Mega/Yenot Bitan presence (verified manually) — not a data bug.
- **`publishprice` portal type (9d-1)** — new base class `scraper/publishprice.py`. JS-embedded file listing pattern. Currently only Carrefour, but reusable.
- **Geo-blocking discovered (9d-1)** — `prices.carrefour.co.il` and `laibcatalog.co.il` (Victory) block non-Israeli IPs. Confirmed by Eltzur via VPN test. Other 5 chains' portals don't enforce this. Migration path TBD in 9g (EU-West region trial first, Israeli VPS as fallback).
- **Scraper performance bottleneck — resolved 9g-1 + 9g-3 (May 17, 2026)** — Old Railway US-West: ~1.5min/store from per-row INSERT round-trips + cross-continent DB writes. Resolved via (a) batched VALUES inserts at 1000 rows/statement across items, item_chain_names, prices tables, (b) deduplication of source-XML duplicate item_codes to prevent Postgres CardinalityViolation on ON CONFLICT, (c) Postgres on same Kamatera VPS as scraper = localhost writes. Result: 58 stores in 3m31s. Scales fine to 216 stores (estimated ~13 min) and 540 stores (estimated ~30 min) without further changes.
- **Shufersal sub-chain landscape (9d-1, field intel from Eltzur)** — same chain_id `7290027600007` publishes: דיל (Deal, mainstream discount), שלי (Sheli, neighborhood), אקספרס (Express, convenience), יש/יש חסד (Yesh, haredi sector — dominates Jerusalem/Bnei Brak), Universe (hypermarket), BE (pharmacy/health). NOT all sub-formats publish individual PriceFull files. "Lowest store_id" selection rule biased toward old Jerusalem Sheli stores in 9d-1 — needs format-aware refactor in 9e.
- **StoreNext: free CSVs only, paid tier rejected (May 17, 2026)** — Free CSV branch lists at `storenext.co.il/תמיכה-ושירות/` remain usable for 9e Registry (store_id, EDI barcode, store name with format prefix, all 7 EDI-using chains). **Paid tier was investigated and rejected: NIS 30K one-time for a single Excel catalog export — pricing doesn't fit pre-revenue stage.** Revisit at scale. GS1 IL is the better-shaped catalog data source going forward.
- **Master brand (xxl.co.il) is the canonical surface (9f)** — xxl.co.il is the portal; verticals are paths on it (`/vacation`, `/fashion`) NOT subdomains. Earlier plans for `fly.xxl.co.il`, `hotel.xxl.co.il` etc. are obsolete.
- **Portal verticals collapsed: חופשות = flights + hotels (9f)** — earlier 4-tile design reduced to 3-tile (מצרכים, חופשות, אופנה). חופשות is the single travel vertical covering both.
- **AI search bar uses mocked keyword router for now (9f)** — `web/src/utils/portalSearchRouter.ts` exports `classifyAndRoute(query)` with hardcoded Hebrew + English keyword lists. Function signature designed for one-line swap to Claude Haiku in 9h.
- **Hostname-based routing in React (9f)** — `App.tsx` has `isPortalHostname()` checking `window.location.hostname`. When true (xxl.co.il / www.xxl.co.il / localhost?portal=1), `/` renders `PortalPage`. When false, falls through to `AppShell`. Briefly tried .htaccess 302 redirect mid-session but rejected — left `/portal-preview` in URL bar.
- **Email signup on בקרוב pages is intentionally dummy (9f)** — `console.log` only. Wiring to real backend deferred to 9f-followup.
- **Offsite backups via Backblaze B2 (May 19, 2026)** — Daily pg_dump custom-format → local `/var/backups/scrp` (rotation: 7 daily, 4 weekly Sundays, 6 monthly 1st-of-month) → uploaded to B2 bucket `xxl-scrp-backups/daily/`. Uses rclone native B2 backend (NOT S3-compat — S3 layer rejects bucket-scoped keys with "not entitled" error due to object-lock metadata queries). Cost: ~$0/mo (10 GB B2 free tier; current ~10 MB/day × 365 = ~3.6 GB/year max with rotation).
- **Shufersal scraper timeout bumped 30s → 60s (May 19, 2026)** — `scraper/shufersal.py:77`. Shufersal's portal goes through slow patches; 30s was tripping on healthy responses. Committed `389bd3e`. Not a fix for actual outages, but improves resilience to slow-but-up days.
- **Rami Levy canonical `sub_chain_id='001'` (9k)** — split-store duplicates merged onto the `001` row (carries name/city). The legacy `sub='1'` rows were pre-9j-followup artifacts; `upsert_store` padding now prevents recurrence.

---
## Operating patterns Established

### Ground Rules (apply to every new chat)

1. **Short responses.** Status or diagnosis, suggested fixes with the
   recommended option marked, then the tasks/commands. No full thought
   process, no mid-chat pivots.
2. **Fool-proof = delegate to Claude Code.** Maximize work handed to CC.
   All prompts in copy-paste code blocks. Keep manual effort to a minimum.
3. **Read previous chats for context** before starting work, to avoid
   repeating past mistakes.
4. **Handoff maintenance is CC's job.** CC updates handoff.md, commits, and
   pushes automatically at session end (and when asked mid-session). The chat
   assistant drafts the entry content; CC owns writing it to the file and
   committing — it's faster and cleaner.

- **One chat = one session** — Long conversations balloon in token cost (cumulative history is re-read every turn, so turn 60 of a chat costs much more than turn 5 of a new one). At natural breakpoints (end of session, deploy verified, phase complete), START A FRESH CHAT and paste handoff.md as the first message. Yesterday's debugging context isn't useful for today's feature work — it's just expensive baggage. Especially: avoid trying to squeeze a new session into an existing long chat just because we're already talking. Lesson learned in 9c when token budget hit limits faster than expected during Phase 2.

### Operating Policies (codified 9d-3 — apply to every new session)

**A. Investigate the source on the web BEFORE designing a workaround.**
When a task needs information we don't have — an endpoint's behavior, a portal's
structure, what data a chain publishes — Claude does NOT reverse-engineer alone.
Claude first asks Eltzur to check the source on the web (portal page, dropdown,
published credentials, docs). Proven in 9d-3: the Shufersal store dropdown and
the gov.il credentials list each replaced a complex workaround with a five-minute
look at the actual website. Default order: identify unknown → ask Eltzur to check
the source → design against real data. Cheaper for both sides, and humans bring
lateral-thinking AI structurally lacks.

**B. CITY_CODES policy — see comment in cerberus.py.**
Real municipalities only. Never regional councils (מועצה אזורית). Never
bulk-import locality.xls (it mixes cities and regional councils). Authoritative
sources: C:\scrp\data\locality.xls (MOI master) and Israel Post's
סמל_ישוב_דואר_ישראל.pdf. DO NOT use kod_yeshuvim_02.xls — it's the CBS
internal serial system, incompatible number space.

**C. CC's "summary instead of data" pattern — always ask for the raw data.**
CC consistently substitutes a confident summary for the raw data it was asked to
produce. Examples from 9d-3: pf_rows[0] (skipped picking newest), "157 doralon
stores, ship it" (hid city-coverage issue), the locality.xls "wrong code system"
verdict (one sheet, didn't check others), "Nahal Sorek MOI dual-name situation"
(hallucinated explanation), three rounds of Fresh Market / Tiv Taam summaries
without tables. When CC sends a summary, ASK FOR THE RAW DATA explicitly and
don't approve until you see it. Use file-redirect (`> outfile.txt`) when stdout
truncates.

**D. CC file-read collapse — ctrl+o expands it.**
When CC reads a file or produces long output, the result often collapses to
"[Read 1 file]" in the VS Code display. The bytes are still there — pressing
ctrl+o in the CC pane expands them. If CC's third reply on the same ask still
has no data, suspect a collapsed read before suspecting CC.

**E. PowerShell stderr handling.**
PowerShell treats any stderr output (including Python's INFO logs) as a
NativeCommandError and shows it in red. Not a failure — judge scripts by stdout.

**F. Hot-path discipline (4 clean commits in 9d-3):**
Read-and-report-STOP on scraper hot paths. Verify mechanism via read-only script
before adding to cron. Multi-stage prompts with STOPs between stages. Single
coherent commit at the end. Worked for both Shufersal and Tiv Taam.

## 🔗 External Data Source Status

- **gov.il price transparency XML** — primary source. Working.
- **Cerberus portal** (`url.retail.publishedprices.co.il`) — used by Yochananof, Keshet, Osher Ad, etc. Login-based.
- **Shufersal direct** (`prices.shufersal.co.il`) — open HTTP, no auth.
- **Rami Levy direct** — open HTTP.
- **Victory** — REST API, custom scraper (~55 lines).
- **OpenFoodFacts** — ❌ ABANDONED. Tested in past sessions, found it out of date and nearly empty for Israeli barcodes. Code exists in repo but do not invest more effort here.
- **StoreNext** — outreach pending (Eltzur left contact details May 12). Free CSV branch lists per chain confirmed working (`storenext.co.il/תמיכה-ושירות/`). Paid tier scope TBD. Will inform 9e Registry session.
- **OpenIsraeliSupermarkets Kaggle dataset** — bookmarked for future price history (9d).

---

## 📂 File Location Reference (portal files added in 9f)

When asking CC to modify portal/supermarket code, here are the key files and what to look for. Line numbers omitted (they drift) — use the descriptive anchors instead.

| File | Purpose | Anchors when modifying |
|---|---|---|
| `web/src/pages/PortalPage.tsx` | Portal landing page | Search for: `<XxlLogoPortal>` hero, rotating placeholder `useEffect` with 4 examples, the 3 vertical tiles (search "מצרכים"), value-props strip (search "חינם לחלוטין"), sub-header "הפורטל שהופך כסף רגיל לכסף חכם" |
| `web/src/pages/ComingSoonPage.tsx` | Shared template for /vacation and /fashion | Email form, regex validation, `console.log('[ComingSoonPage] Email signup:', ...)` — this is the line 9f-followup replaces with real backend |
| `web/src/pages/VacationPage.tsx` | Thin wrapper passing חופשות + Sun icon to ComingSoonPage | — |
| `web/src/pages/FashionPage.tsx` | Thin wrapper passing אופנה + Shirt icon to ComingSoonPage | — |
| `web/src/components/XxlLogoPortal.tsx` | Portal animated logo (duplicate of XxlLogo.tsx with portal tagline) | Tagline "קונים חכם · חוסכים בענקקק" on SVG textPath, fontSize 28, letterSpacing -0.5. sessionStorage key `xxl_portal_animated_this_session`. |
| `web/src/components/XxlLogo.tsx` | Supermarket app logo — **DO NOT modify for portal changes** | Hardcoded tagline "חוסכים בענקקק". Duplicate this file if a new tagline is needed elsewhere. |
| `web/src/utils/portalSearchRouter.ts` | Mocked AI intent classifier | Exports `classifyAndRoute(query)`. **Swap this function body when wiring Claude Haiku in 9h** — keep the signature. |
| `web/src/App.tsx` | Top-level routing + hostname detection | `isPortalHostname()` at top of file. Top-level `<Routes>` with portal routes, conditional `/`, and `/*` catch-all → `<AppShell />`. AppShell wraps the supermarket app with its own internal `<Routes>`. |
| Hostinger `public_html/.htaccess` | Server-level routing (NOT in repo) | Minimal React Router SPA fallback only. If adding server-level rules later (cache headers etc.), insert BEFORE the SPA fallback block. |

---
```
### Session 9j-followup (May 21, 2026) — City Matcher Ported to Scrapers + store_id Padding

**Done:**
- Created `scraper/city_matcher.py` — the 9j matcher logic (city dictionary, abbreviation expansion, sub-format prefix stripping, per-chain matchers, Hebrew-safe boundary matching) extracted into a reusable module. Public API: `resolve_city(store_name, address, chain_id) -> (city, confidence)`. Verified against the 355-store 9j dataset: identical results (296 high-confidence matches).
- Wired `resolve_city` as a fallback into both scraper store-load paths (`cerberus.py`, `publishprice.py`): when the numeric government city-code lookup returns nothing, the matcher fills `city` if confidence ≥0.80. New stores now get a city at scrape time instead of accumulating as NULLs. (This was step 5 of the original 9j plan.)
- `store_id` / `sub_chain_id` padding normalization: `publishprice.py` historically stored Carrefour store_ids unpadded (`'6'`) while `cerberus.py` zero-padded (`'006'`). Changed `publishprice.py` to zero-pad (2 spots); `db.py` `upsert_store` now defensively pads via `_pad_store_id`. Ran `migrate_store_id_padding.py` — **40 Carrefour rows migrated** to canonical 3-digit format.
- Server hotfix committed: Shufersal `_fetch_raw_page` timeout 30s→60s (was applied directly on server during 9g, never committed).

**NEW BUG FOUND (logged as session 9k):**
- The padding migration surfaced 14 "collision" rows — Rami Levy stores that exist twice (`sub_chain_id='1'` and `'001'`). Investigation showed **both copies carry prices** (~8K rows each) — the catalog is split across duplicate store records. This is a data-integrity bug affecting basket comparison. See 9k pending session above. The migration correctly skipped these 14 rather than auto-merging.

**Scripts:** `migrate_store_id_padding.py` committed to repo root. The 9j one-shot scripts (`apply_matches.py`, `fix_9j_residual.py`, `fix_ramilevy.py`, `normalize_cities.py`, `review_matches.py`) remain untracked local artifacts per the Option-A decision.

**Files changed:** `scraper/city_matcher.py` (new), `scraper/publishprice.py`, `scraper/cerberus.py`, `db/db.py`, `scraper/shufersal.py`, `migrate_store_id_padding.py` (new).

**Note on Claude Code:** CC initially generated its own simplified `city_matcher.py` from scratch (the real file wasn't in its prompt) — caught and overwritten with the correct tested version. Lesson: when handing CC a pre-built file, save it first and tell CC explicitly not to recreate it.
```

### Session 9j (May 21, 2026) — City Field Normalization

**Goal:** resolve 355 stores with NULL `city` via progressive auto-matching.

**Done:**
- Built `normalize_cities.py` — a per-chain city matcher: city dictionary (~190 Hebrew cities), abbreviation expansion (כ"ס→כפר סבא, ראשל"צ→ראשון לציון, etc.), Shufersal sub-format prefix stripping (שלי/דיל/אקספרס/BE/יש חסד), Hebrew-safe word-boundary matching. Output: `matches.csv` with per-store confidence scores. No DB writes — analysis only.
- Auto-matcher resolved 299/355 (84%), 296 at confidence ≥0.80. Eltzur manually reviewed `matches.csv` in Excel and corrected/filled ~50 rows (everything below 90% confidence), bringing it to 350 clean fills.
- Built `apply_matches.py` — dry-run + `--commit` modes, updates `city`/`city_norm` only where currently NULL. Committed: 318 rows + 1 online store moved to `sub_chain_id=1234`.
- Built `fix_9j_residual.py` — fixed 14 Carrefour stores skipped due to `store_id` format mismatch + deleted 2 orphaned Yochananof rows (150/152, renumbered to 50/52).
- Built `fix_ramilevy.py` — fixed 14 Rami Levy stores skipped because the DB stored them with `sub_chain_id='1'` while the apply script padded to `'001'`.
- **Result: 349/355 resolved. 6 NULL remain, all intentional** — Shufersal 000, Yochananof 002 (יוחננוף ישן), Keshet 102-105 (Kulinarik). Final city coverage: 827/833 stores = 99.3%.

**Decisions made:**
- Online stores (e.g. Shufersal ONLINE) → `city='אונליין'`, moved to reserved `sub_chain_id='1234'`.
- Kulinarik (Keshet store_ids 102-105) — identified as a separate chain (would-be chain_id `7690058200000`), but **left as Keshet rows for now**; too small to be worth a migration. Revisit if Kulinarik grows.
- Yochananof pickup points 150/152 were the wrong store codes — corrected to 50/52, old rows deleted.

**Bugs found (logged as pending work):**
- Scrapers don't populate `city` on new stores → `9j-followup` 
- `stores.sub_chain_id` / `store_id` format inconsistency caused two apply-script silent skips → `stores table data hygiene` pending session.

**Corrections to this handoff:**
- Rami Levy chain_id was wrong here (`7290058108879` — that's actually KingStore per Kaggle). **Correct Rami Levy chain_id: `7290058140886`.** Fixed throughout where it appears.

**Scripts:** all four live in `~/scrp/scripts/` on Kamatera and `C:\scrp\` locally:
`normalize_cities.py`, `review_matches.py`, `apply_matches.py`, `fix_9j_residual.py`, `fix_ramilevy.py`.


### Session 8L (April 29, 2026) — Brand Identity & Animated Logo

**Done:**
- Brand strategy: chose master `xxl.co.il` brand-first approach (Option B). Bold/energetic personality. Hebrew-native naming.
- Brand identity finalized:
  - **Name:** XXL (Latin wordmark)
  - **Hebrew tagline:** חוסכים בענקקק (with stretched ק's for "saving big" emphasis — tagline arches over the wordmark)
  - **English tagline:** SAVING **BIG** (2× size ratio between SAVING and BIG)
  - **Personality:** Fast & Furious — speed lines, hard slam entrance, basketball-team-banner-break energy
- Color palette codified:
  - Primary emerald: `#059669` (Tailwind emerald-600)
  - Shadow emerald: `#064E3B` (Tailwind emerald-900)
  - Accent orange: `#EA580C` (Tailwind orange-600)
  - Dark text: `#022C22`
- Typography: **Rubik** (Hebrew + Latin) at weight 900 italic for the wordmark, weight 900 upright for tagline. Font preloaded from Google Fonts.
- Animation choreography (1.5s total, plays once per session via `sessionStorage`):
  - 0.0–0.4s: Speed lines streak in from both sides (orange left, emerald right, staggered)
  - 0.45–1.45s: XXL slams in from above with 1.85× overshoot, deep squash to 0.78×, hard rebound to 1.18×, settle to 1×. Camera shake on impact (7px range), white flash (95% opacity), shadow layer materializes in sync.
  - 1.45–2.15s: Tagline appears above with fade + subtle slide-down
- React component `XxlLogo.tsx` with three variants: `hero` (large animated), `header` (small static), `favicon` (XXL-only stripped down). Accepts `lang` prop for Hebrew/English tagline switch.
- Hero section added above search bar on homepage.
- Header text "השוואת מחירים בסופרמרקט" replaced with static XXL header logo. Removed redundant ShoppingCart decorative icon.
- Custom favicon.svg created (XXL wordmark + shadow, no tagline).
- Page title updated to `XXL — חוסכים בענקקק`.

**Decisions made:**
- Master-brand-first strategy (Option B) chosen over per-vertical branding to ensure visual coherence across future xxl.co.il subdomains (fly, hotel, fashion).
- "Pure slam" animation chosen over "paper banner break" variant — pure version ages better, less visual complexity, more brand-mark-iconic.
- English tagline kept as 2× size jump (SAVING vs BIG) rather than 3× — clean ratio, avoids verticality issues.
- Animation runs once per session (via `sessionStorage.getItem('xxl_animated_this_session')`), not per page load — encourages "first impression" feel without becoming annoying on navigation.
- React `useId()` hook used for unique SVG path IDs (with colon-stripping to ensure XML validity) — prevents id clashes when both header and hero variants are on the same page.

**Outcome:** Site now has a distinctive, ownable brand identity. Animated hero on first session load, static logo in header, custom favicon, browser tab title updated. All brand decisions documented and codified in code (no more loose hex codes scattered through the app).

**Next:** Session 9b — User authentication (signup flow, login, account management). The "הירשמו" CTA button on the basket-limit toast will finally do something real.

### Planning Session (April 30, 2026) — Strategy & Roadmap Refinement

**Done (no code shipped, planning only):**
- Discussed multi-PC continuation workflow (clone repo + handoff.md = ready to work)
- Confirmed GitHub backup status — code safe, but Railway DB is single-point-of-failure (mitigation deferred to post-9c)
- Detailed analysis of "all 700 stores" tradeoff — decided to expand in tiers
- **Long-term vision clarified:** Premium tier will eventually include cross-chain ordering (~12+ months out), which requires full coverage and chain partnerships. Documented as future direction, not in current scope.
- Confirmed OpenFoodFacts is **abandoned** (was already in handoff but reinforced) — out of date, nearly empty for Israeli barcodes.
- Researched Israeli city populations (CBS data via web search): 18 cities >100K, ~45-50 cities >50K
- Locked the **city expansion plan**:

**City Expansion Plan (Sessions 9d-1 through 9d-N):**

Phase 1 — Session 9d-1 (Option C, geographic diversity):
- New cities: Tel Aviv-Yafo, Haifa, Be'er Sheva, Rishon LeZion, Ashdod
- Existing: Jerusalem, Bnei Brak (unchanged)
- 2 stores per chain per city → ~60 new stores
- Total post-rollout: ~86 stores across 7 cities
- Goal: validate scraper performance + Cerberus rate limits before scaling

Phase 2+ — Sessions 9d-2 onward:
- Expand to remaining 100K+ cities (12 more): Petah Tikva, Netanya, Holon, Ramat Gan, Ashkelon, Rehovot, Bat Yam, Beit Shemesh, Kfar Saba, Herzliya, Modi'in
- Target end-state for "100K+ tier": 18 cities × 6 chains × 2 stores = ~216 stores

Phase 3+ — Sessions 11+:
- Expand to 50K+ population cities (~25-30 more)
- Total target: ~540 stores

**Decisions made:**
- **Tier-based city expansion** beats "everything at once" — controls risk, gives natural scaling milestones, validates infra at each step
- **Defer infrastructure migration** — stay on Railway until $20+/mo costs OR DB > 8GB OR scrape > 4hrs OR >1000 active monthly users. Then migrate to AWS/GCP.
- **9b (user auth) remains the priority** — keystone for 9c (freemium) and unlocks the "save my basket" retention feature. Will be tackled before city expansion phases.
- **Auth approach for 9b:** Email/password primary + Google OAuth as option (decided yesterday).
- **OpenFoodFacts:** Will not retry. Code stays in repo for archaeological purposes only.
- **Premium ordering vision:** Acknowledged as long-term (12+ months), not blocking near-term sessions.

**Outcome:** Roadmap clarified, scope locked, ready to execute. No code changes, but the next session can start immediately with a clear plan.

**Next:** Session 9b — User authentication (email/password + Google OAuth). After 9b, evaluate whether to do 9c (freemium gating) or 9d-1 (city phase 1) next based on energy/mood.

### Session 9b (April 30, 2026) — User Authentication via Supabase + Saved Baskets

**Done:**
- **Supabase project provisioned** at https://dwohlwmiejgjlsbuegeu.supabase.co (Frankfurt region, free tier, ~50K MAU limit)
- **Database migration applied to Railway Postgres**: new `users` table (PK = Supabase UUID) and `saved_baskets` table (FK to users with ON DELETE CASCADE, JSONB items column, indexed by user_id). Migration file at `db/migrations/add_users_saved_baskets.sql`.
- **Backend (FastAPI):**
  - `api/auth.py` — JWT verification dependency + idempotent user upsert on every authed request
  - `api/routers/saved_baskets.py` — full CRUD (`POST/GET/GET-by-id/PUT/DELETE`) with ownership enforcement (404 on user_id mismatch, NOT 403, to avoid leaking basket existence)
  - Endpoints exposed at `/baskets` (no `/api/` prefix — matches existing `/basket/compare` pattern)
- **Frontend (React + Vite):**
  - Supabase client at `web/src/lib/supabase.ts` (anon public key in `VITE_SUPABASE_ANON_KEY`)
  - `AuthContext.tsx` — exposes `useAuth()` with user, signIn, signUp, signOut, accessToken
  - React Router added with routes `/`, `/login`, `/signup`, `/baskets`
  - HomePage extracted from old App.tsx into `pages/HomePage.tsx`
  - LoginPage, SignupPage, MyBasketsPage created (all RTL Hebrew, brand-emerald CTAs)
  - Header.tsx made auth-aware: logged-out shows "להרשמה" (emerald button) + "התחברות" links; logged-in shows User icon dropdown with email + "הסלים שלי" + "התנתקות"
  - BasketDrawer.tsx: "שמור סל" button (enabled when logged in, disabled with tooltip when logged out)
  - BasketContext.tsx: 25-item-limit toast CTA wired to `navigate('/signup')` (was placeholder console.log in 9a)
  - api/client.ts: axios interceptor automatically attaches `Authorization: Bearer <token>` to all requests when user is logged in
  - display_name field removed from signup (was being collected but not persisted — UX wart, removed per Eltzur direction)

**Deployment notes:**
- `.gitignore` had a generic `lib/` rule that accidentally caught `web/src/lib/supabase.ts`. Fixed by adding `!web/src/lib/` and `!web/src/lib/**` whitelist rules.
- `web/.env.development` and `web/.env.production` both contain `VITE_SUPABASE_URL` and `VITE_SUPABASE_ANON_KEY`. Properly gitignored — keys never reach the public repo.
- Railway env vars: `SUPABASE_URL`, `SUPABASE_ANON_KEY`, `SUPABASE_JWT_SECRET` all set on the `web` service.
- Frontend bundle grew from 402 KB → 665 KB (+260 KB Supabase SDK). Worth code-splitting later but not urgent.

**Decisions made:**
- **Auth library: Supabase** (Option B from the planning session) — battle-tested, free up to 50K MAU, handles password hashing / sessions / reset emails / OAuth providers. Vendor dependency accepted.
- **User data stays in Railway Postgres**, not Supabase DB — Supabase is auth-only. Foreign keys to baskets/favorites/etc. all live in Railway. Single source of truth for app data.
- **Routes over modals** for signup/login — easier to build correctly in RTL, better SEO, easier to deep-link.
- **Email confirmation: KEPT ENABLED** despite original spec to disable. Reasoning: security best practice, low friction, Supabase enforces it for the first user creation regardless of toggle. Decision: leave it on permanently.
- **Google OAuth: DEFERRED.** Email/password is working; Google requires a Google Cloud Console OAuth client setup. Will be added in a follow-up session, NOT 9c.
- **JWT verification migrated to ES256/JWKS** mid-deploy. Supabase recently switched from HS256 (shared secret) to ES256 (asymmetric public-key crypto). Original CC code assumed HS256, which caused all authed requests to 401. Backend rewrite to use `https://{SUPABASE_URL}/auth/v1/.well-known/jwks.json` for verification. Fixed in-session.
- **404 not 403 on basket ownership mismatch** — security pattern, prevents leaking that a basket exists.
- **No `/api/` prefix** on basket endpoints — matched existing `/basket/compare` pattern.

**Bugs encountered & resolved:**
1. ✅ CC's terminal report displayed Hebrew strings reversed character-by-character (RTL/LTR rendering bug). The actual code was correct. Verified via VS Code Find.
2. ✅ `web/src/lib/supabase.ts` was caught by the catch-all `lib/` rule in `.gitignore`. Whitelisted with `!web/src/lib/`.
3. ✅ JWT signing algorithm mismatch (Supabase ES256 vs backend HS256) — fixed via JWKS-based public-key verification in api/auth.py.
4. ✅ Email confirmation flow — Supabase still required email verification for the first signup despite the dashboard toggle. Resolved by clicking the confirmation link in email.
5. ⚠️ Favicon stale in some browsers — file is correct on Hostinger and source code, but browser cache holds onto the old Vite lightning bolt favicon. Will resolve naturally for new visitors. Local fix: clear site data + reload.
6. ✅ Database tables disappeared between morning and evening of session 9b (root cause unknown — Railway Postgres may have been reprovisioned, or migration ran on a stale connection). Re-ran migration manually via Railway Query editor — both tables came back, no data loss since tables were never populated. Investigate before next session.
7. ✅ SQL parameter binding bug in saved_baskets endpoints — original code mixed psycopg2-style `%(name)s` with SQLAlchemy `:name` style, AND used `::jsonb` cast which collided with SQLAlchemy's parameter scanner. Fixed by standardizing on SQLAlchemy `:name` style and using `CAST(:items AS jsonb)` instead of `:items::jsonb`. Both POST and PUT endpoints had the bug; both fixed.
**Files changed:**
- New: `api/auth.py`, `api/routers/saved_baskets.py`, `db/migrations/add_users_saved_baskets.sql`, `web/src/components/AuthContext.tsx`, `web/src/lib/supabase.ts`, `web/src/pages/HomePage.tsx`, `web/src/pages/LoginPage.tsx`, `web/src/pages/SignupPage.tsx`, `web/src/pages/MyBasketsPage.tsx`
- Modified: `api/main.py`, `requirements.txt`, `web/package.json`, `web/package-lock.json`, `web/src/App.tsx`, `web/src/main.tsx`, `web/src/api/client.ts`, `web/src/components/BasketContext.tsx`, `web/src/components/BasketDrawer.tsx`, `web/src/components/Header.tsx`, `.gitignore`

**Outcome:**
- ✅ Email/password signup + login working in production
- ✅ User auth state correctly reflected in header (account icon dropdown when logged in)
- ✅ 25-item toast CTA correctly navigates to /signup
- ✅ Save-basket: working end-to-end — POST /baskets returns saved basket with id, frontend renders success toast
- ✅ My-baskets list view: working — basket appears at /baskets with name, item count, last updated date, "טען" and "מחק" buttons
- ✅ Favicon: confirmed working in incognito after the recent deploy. Hard reload was needed for already-cached browsers; new visitors see XXL favicon by default

**Next:** Once save-basket verified working in production, update the Outcome bullets above. Then move to either:
- **9c (Freemium gating)** — differentiate free vs paid tier (the 25-item limit currently applies to logged-in users too, which doesn't make sense for paying customers)
- **9d-1 (City phase 1)** — add 5 new cities × 6 chains × 2 stores = ~60 new stores, brings total to ~86 stores across 7 cities
- **Google OAuth follow-up** — wire up the option that was deferred from 9b

Recommended order: 9c next (small, completes the auth → freemium picture before building more features). Then either 9d-1 or Google OAuth.


### Planning Session (May 2, 2026) — 9c Scope Refinement

**Done (planning + scoping, code coming next):**
- Reviewed handoff and confirmed 9b shipped successfully (auth + saved baskets all green in production)
- Reviewed the original 9c plan ("freemium gating, server-side 25-item limit per account") and concluded it was misaligned with the freemium model that was actually decided in session 9a (everything-but-ordering is free)
- Restructured 9c into two phases:
  - **Phase 1 (Mini-9c):** Lift 25-item basket cap to 150 for logged-in users. Logged-out users stay at 25 with the existing emerald להרשמה toast. Logged-in users at 150 see a brief amber/orange toast "הסל הגיע למקסימום של 150 פריטים" — no CTA, no signup nudge.
  - **Phase 2 (Engagement features):** Favorites (server-side, logged-in only) + Recent Searches (localStorage, search-bar dropdown only).

**Scope decisions for Phase 2:**
- **Favorites:** Logged-in only (cleanest). New `favorites` table (user_id, barcode, created_at, composite PK). Endpoints `POST /favorites/{barcode}`, `GET /favorites`, `DELETE /favorites/{barcode}`. Star icon on ProductCard. New `/favorites` route + page. "המועדפים שלי" link in account dropdown.
- **Recent Searches:** Client-side only (localStorage, max 10 items, deduped). Dropdown shown when search input is focused and empty. Path 1 from earlier scoping — Path 2 (server-side sync) deferred indefinitely; if users ask for cross-device sync, we add it then.

**Decisions made:**
- **Logged-in basket cap = 150** — generous enough that no real human will hit it, low enough to prevent runaway client memory in pathological cases.
- **No server-side enforcement of basket cap** — frontend check is sufficient; we'll add server-side validation only if/when we see abuse.
- **No CTA button on the 150-cap toast** — different intent from the signup nudge; this is just a "you've hit the ceiling, sorry" message. Orange/amber instead of brand emerald to visually differentiate.
- **Favorites is server-side from day 1** — unlike recent searches, favorites are about cross-device persistence. Users expect their stars to follow them.
- **Skipped: Database migration mystery investigation** — Eltzur decided to defer pending future AWS/GCP migration, where this becomes moot.

**Out of scope for 9c (deferred to future sessions):**
- Multiple named baskets (e.g., "Weekly", "Shabbat") — interesting but no clear user demand yet
- Saved-basket renaming/duplication — minor polish
- Basket sharing via public link — interesting but post-monetization
- Price-drop notifications UI — paid tier feature, comes with the email infrastructure
- Google OAuth — still deferred from 9b, will tackle separately when we have appetite for Google Cloud Console setup
- Server-side recent searches sync — only if users ask

**Outcome:** 9c scope locked, two CC prompts ready (Phase 1 surgical, Phase 2 larger). Each phase ships independently — Phase 1 is frontend-only (one file), Phase 2 touches multiple files (backend migration + endpoints + frontend pages).

**Next:** Run Phase 1 → deploy → test → run Phase 2 → deploy → test. Then session 9d-1 (city + chain expansion).


### Session 9c (May 2, 2026) — Mini-9c + Favorites + Recent Searches

**Done:**
- **Phase 1 (Mini-9c)**: Logged-in users now have a 150-item basket cap (vs 25 for logged-out). Logged-in cap-hit fires an amber/orange (#EA580C) Sonner toast "הסל הגיע למקסימום של 150 פריטים" with no CTA. Logged-out 25-item toast with "להרשמה" emerald CTA preserved exactly as before.
- **Phase 2A (Favorites — server-side, logged-in only)**:
  - New `favorites` table (composite PK on user_id + barcode, FK to users with ON DELETE CASCADE)
  - New endpoints: `POST /favorites/{barcode}` (toggle, idempotent), `GET /favorites` (list with item details), `DELETE /favorites/{barcode}` — all auth-required, queries inherently scoped via composite PK
  - New `FavoritesContext` with optimistic toggle + revert-on-error
  - Heart icon (lucide-react `Heart`) on every ProductCard, top-right of badge row. Brand orange (#EA580C) when filled, gray-300 outlined when not
  - Logged-out users clicking heart get a toast "התחברו כדי לסמן מועדפים" with "להתחברות" CTA → /login
  - New `/favorites` page rendering favorited items as ProductCards (auth-required, redirects to /login if not authed)
  - "המועדפים שלי" link added to account dropdown in Header
- **Phase 2B (Recent Searches — client-side, dropdown only)**:
  - New `useRecentSearches` hook backed by localStorage (key: `xxl_recent_searches`)
  - Stores up to 10 most recent unique queries (case-insensitive dedup, trims, ignores < 2 char), most recent first
  - Dropdown appears when search input is FOCUSED + EMPTY + has at least one entry
  - Each row: query text + × to remove that one. "נקה הכל" link to clear all
  - Click row → fills input + triggers search. `onMouseDown: e.preventDefault()` on dropdown items prevents blur-before-click race
- **Cheapest indicator visual fix**: Replaced the in-row star (which collided visually with the favorite star) with `CheckCircle2` (outlined, emerald-600). No more double-star ambiguity.

**Decisions made:**
- **Logged-in cap = 150**: generous enough no human hits it, low enough to prevent runaway memory in pathological cases.
- **No server-side enforcement of basket cap**: frontend check sufficient until abuse seen.
- **Favorites server-side, recent searches client-side**: favorites are about cross-device persistence (users expect stars to follow them); recent searches are ephemeral and per-device. Path 1 (localStorage) for searches kept scope tight.
- **FavoritesPage uses N+1 fetch pattern** (Promise.allSettled per favorite): acceptable for typical usage (<50 favorites). If users hit much higher counts, build a `/product/batch?barcodes=...` endpoint.
- **Heart in brand orange (#EA580C), not red**: cohesive with XXL palette (orange already used in logo speed lines + basket-limit toast). Avoids red's "danger" connotation in a savings-positive context.
- **CheckCircle2 outlined, not filled**: subtler than a filled badge. Lets the row itself (with emerald-50 background) carry the "cheapest" signal; the icon is just confirmation.
- **Original "freemium gating" 9c framing retired**: no server-side per-account 25-item enforcement. The free tier is the honeypot; only logged-out users see the 25-item nudge as a signup driver.

**Files changed:**
- New: `db/migrations/add_favorites.sql`, `api/routers/favorites.py`, `web/src/components/FavoritesContext.tsx`, `web/src/pages/FavoritesPage.tsx`, `web/src/hooks/useRecentSearches.ts`
- Modified: `api/main.py`, `web/src/api/client.ts`, `web/src/App.tsx`, `web/src/components/Header.tsx`, `web/src/components/ProductCard.tsx`, `web/src/components/SearchBar.tsx`, `web/src/components/BasketContext.tsx`

**Bugs encountered & resolved:**
1. ✅ Initial CC implementation reused the existing `Star` icon for both "favorites" and "cheapest indicator" — visually ambiguous. Caught during sanity check, swapped to `Heart` (favorites) and `CheckCircle2` (cheapest) before deploy.
2. ⚠️ False alarm: CC's terminal report rendered Hebrew strings reversed (e.g., `ילש םיפדעומה` instead of `המועדפים שלי`). Verified via VS Code Find that file content is correct. Same RTL terminal display bug seen in 9b and 9c Phase 1. **From now on, treat reversed-Hebrew in CC reports as a non-issue unless VS Code Find can't locate the correctly-spelled string.**

**Outcome:**
- ✅ Phase 1 verified: logged-out 25-cap toast unchanged (regression test passed); logged-in 150-cap toast fires correctly with orange styling
- ✅ Phase 2A verified: heart toggles, persists across reload, /favorites page renders, dropdown link works
- ✅ Phase 2B verified: recent searches stored, dropdown appears on empty-focused input, click re-runs search, × removes individual, "נקה הכל" clears all
- ✅ Cheapest indicator visual fix in production

### Session 9f-followup (May 14, 2026) — Portal Polish

**Done:**
- Hostname-aware SEO meta tags (title/description/OG/Twitter cards differ for xxl.co.il vs super.xxl.co.il). Static tags in index.html default to portal; runtime override in App.tsx via `seoMeta.applyHostnameMeta()` switches to supermarket-app variant on super.xxl.co.il.
- OG image URLs reference `/og-portal.png` (xxl.co.il) and `/og-super.png` (super.xxl.co.il) — 1200×630 PNGs uploaded separately by Eltzur to Hostinger public_html/.
- Portal email signup (ComingSoonPage on /vacation + /fashion) now writes to Supabase `portal_email_signups` table via supabase-js. Anonymous insert allowed via RLS + explicit GRANT (future-proof for Oct 30 Data API policy change).
- GA4 wired via VITE_GA_MEASUREMENT_ID env var. Pageviews tracked manually on SPA route changes (gtag config has send_page_view: false). Idempotent init, gated on cookie consent.
- Minimal Hebrew cookie banner ("נמשיך, אנו משתמשים בעוגיות לשיפור החוויה") with X-dismiss-as-consent. localStorage key: `xxl_cookie_consent`. Banner only renders when key absent.
- `isPortalHostname()` refactored from App.tsx-inline to `web/src/utils/hostname.ts` for reuse by seoMeta.ts.

**Decisions made:**
- Cookie banner X-dismiss = implicit consent (per Eltzur, soft-launch UX over strict GDPR-style explicit opt-in). IL-targeted product; revisit if/when expanding to EU users.
- One GA4 property covers both hostnames; filter in reports by page_location host.
- Supabase direct write from frontend (not via FastAPI endpoint) — anonymous signup, no auth flow needed, simpler. Explicit GRANT statements in migration to future-proof against Oct 30 Data API policy default change.
- Static fallback meta tags default to portal version (xxl.co.il) since it's the new marketing surface; super.xxl.co.il SEO is well-established already and SPA crawlers (Google) execute the JS overrides anyway.
- Did NOT modify XxlLogo.tsx or XxlLogoPortal.tsx — favicon decision was "same XXL logo for both," which means no work needed since existing favicon already serves both.

**Files changed:**
- New: `web/src/utils/seoMeta.ts`, `web/src/utils/hostname.ts`, `web/src/utils/analytics.ts`, `web/src/components/CookieBanner.tsx`, `db/migrations/9f_followup_portal_email_signups.sql`, `web/.env.example`
- Modified: `web/index.html` (meta tags), `web/src/App.tsx` (hostname import + useEffect for meta/GA + CookieBanner mount), `web/src/pages/ComingSoonPage.tsx` (Supabase insert + vertical prop), `web/src/pages/VacationPage.tsx` + `FashionPage.tsx` (vertical prop), `web/.env.production` (VITE_GA_MEASUREMENT_ID), `web/.gitignore` (!.env.example exception)

**Outcome:**
- ✅ SEO meta tags hostname-aware
- ✅ OG image refs in place (PNGs to be uploaded separately by Eltzur)
- ✅ Email signups persist to Supabase
- ✅ GA4 stub wired, awaiting Eltzur's real G-XXXXXXXXXX
- ✅ Cookie banner shipped

**Pending Eltzur post-deploy:**
1. Run `db/migrations/9f_followup_portal_email_signups.sql` in Supabase SQL Editor
2. Upload `og-portal.png` + `og-super.png` to Hostinger public_html/ (1200×630 each)
3. Create GA4 property → grab G-XXXXXXXXXX → swap into `web/.env.production` → rebuild + redeploy
4. Mobile QA: test /vacation + /fashion signup on real phone, verify WhatsApp link preview after PNGs uploaded, verify cookie banner dismiss works
**Post-deploy state (end of session):**
- ✅ SQL migration ran successfully in Supabase
- ✅ GA4 wired with real Measurement ID G-YB4X4E5ZKM (baked into web/.env.production)
- ✅ OG images uploaded to Hostinger public_html/ (og-portal.png, og-super.png)
- ✅ Cookie banner verified live on xxl.co.il
- ✅ Test email signup verified landing in portal_email_signups table
- ⏳ Mobile QA pass on real device — deferred
- ⏳ WhatsApp link preview shows title+desc but no image on first scrape — likely Facebook scraper cache. Fix via https://developers.facebook.com/tools/debug → paste URL → Scrape Again. Defer until pre-marketing-push.

**Incident note:** og-super.png initially returned blank/404 due to filename typo during upload to Hostinger. Re-uploaded correctly via File Manager. Lesson: when uploading single files manually to Hostinger, double-check filenames against the index.html meta references — a typo there fails silently (blank response, not 404).

---

### Session 9f (May 12-13, 2026) — XXL Portal Page → Live on xxl.co.il

**Done:**
- **Designed and built the xxl.co.il portal landing page**: hero with animated logo, AI search bar (rotating placeholders), 3 vertical tiles (מצרכים live, חופשות + אופנה בקרוב), value-props strip, footer.
- **3-tile design (down from initial 4-tile)**: collapsed flights + hotels into "חופשות — טיסות ומלונות" with Sun icon. אופנה uses Shirt icon. מצרכים uses ShoppingCart with emerald LIVE badge.
- **Mocked AI search router shipped**: `portalSearchRouter.ts` with Hebrew + English keyword lists. Groceries → external nav to super.xxl.co.il, vacation/fashion → internal React Router, unknown → Hebrew error hint.
- **2 בקרוב sub-pages live** at `/vacation` and `/fashion`: hero + email signup card + "חזרה לדף הבית" link. Email signup `console.log` only (intentional, real wiring deferred to 9f-followup).
- **XxlLogoPortal component created** as duplicate of XxlLogo.tsx with tagline "קונים חכם · חוסכים בענקקק" arching above wordmark. fontSize 28 + letterSpacing -0.5 to fit longer string. Distinct sessionStorage key.
- **Sub-header polish**: "XXL — הפורטל שהופך כסף רגיל לכסף חכם" → final "הפורטל שהופך כסף רגיל לכסף חכם" (dropped XXL prefix; logo above establishes brand). `text-2xl md:text-4xl font-bold`.
- **Hebrew default fixed**: app was loading English on first visit. Now defaults Hebrew with localStorage preservation of user's explicit choice.
- **DNS setup**: A records at box.co.il for `xxl.co.il` and `www.xxl.co.il` → `82.198.227.247`. MX records for Titan email kept untouched.
- **Hostinger parked domain**: `xxl.co.il` parked on top of `super.xxl.co.il`. Both serve from same `public_html/`.
- **SSL**: Lifetime SSL auto-provisioned for `xxl.co.il` within ~30 min of parking.
- **Hostname-based routing in React (final approach)**: `App.tsx` checks `window.location.hostname`; on xxl.co.il, `/` renders PortalPage. Clean URL — `xxl.co.il/` shows portal at `xxl.co.il/`, no `/portal-preview` suffix.
- **Local dev override**: `localhost?portal=1` simulates portal hostname for testing.
- **Two deploys to Hostinger this session**: first got portal pages onto production; second finalized clean URLs after hostname routing change.

**Decisions made:**
- **Multi-vertical portal = paths on xxl.co.il, NOT subdomains**. Simpler routing, one codebase, one deploy.
- **חופשות collapses flights + hotels** — cleaner UX, matches how Israeli travelers actually shop (package vacations).
- **Mocked keyword router over real Haiku for MVP** — ships UI without API key complexity; Haiku becomes its own clean session (9h).
- **Email signup intentionally dummy at launch** — soft-launch acceptance: low signup volume expected, easier to wire backend later than delay launch.
- **Hostname-based routing in React (not .htaccess)** — `.htaccess` 302 redirect approach worked but left `/portal-preview` in URL bar. Final: hostname detection in React, .htaccess back to minimal SPA fallback only.
- **Softened "freemium" claim on value-props**: "ההשוואה תמיד חינם, ללא הגבלות" → "ההשוואה תמיד חינם" (no "unlimited" claim, since 25-item cap exists for logged-out users).
- **XxlLogo.tsx untouched, XxlLogoPortal duplicated** — keeps super.xxl.co.il logo 100% safe from portal changes. Code duplication accepted as right tradeoff for visual isolation.

**Files changed:**
- New: `web/src/pages/PortalPage.tsx`, `web/src/pages/ComingSoonPage.tsx`, `web/src/pages/VacationPage.tsx`, `web/src/pages/FashionPage.tsx`, `web/src/components/XxlLogoPortal.tsx`, `web/src/utils/portalSearchRouter.ts`
- Modified: `web/src/App.tsx` — added `isPortalHostname()` at top, restructured top-level `<Routes>` to include portal routes + conditional `/` for portal hostname + catch-all to `AppShell`. Existing supermarket logic preserved inside AppShell.
- Modified: supermarket app's language initialization logic — now defaults Hebrew when no localStorage preference, preserves user choice when set.
- Hostinger-side (not in repo): `.htaccess` briefly held portal-rewrite block mid-session, ended at minimal SPA fallback only.

**Bugs encountered & resolved:**
1. ✅ **Tagline clipping on portal logo arc** — "קונים חכם · חוסכים בענקקק" is ~60% longer than original. First fix (fontSize 42 → 36) insufficient. Final: fontSize 28 + letterSpacing -0.5.
2. ✅ **First parked domain typo** — entered `xxk.co.il` instead of `xxl.co.il` in Hostinger. Caught before clicking nameserver-change guide (would have wiped DNS records). Deleted typo entry, re-added correctly.
3. ✅ **.htaccess 302 redirect approach** — initial `^$` pattern didn't match Apache root requests on Hostinger's config. Fixed with `^/?$` + `[R=302]`, which worked but left "/portal-preview" in URL bar. Final work replaced this entirely with React hostname detection.
4. ✅ **English-by-default on first load** — language init defaulted to 'en'. Fixed to default Hebrew while preserving localStorage choice.
5. ✅ **Two `.htaccess` files after zip extraction** — Vite generates `.htaccess` in dist/. Resolved by deleting redundant copy.

**Outcome:**
- ✅ https://xxl.co.il loads portal at clean root URL
- ✅ https://www.xxl.co.il same
- ✅ https://xxl.co.il/vacation and /fashion show בקרוב pages
- ✅ https://super.xxl.co.il/ unchanged, Hebrew default
- ✅ SSL active on both (Lifetime)
- ✅ All React Router routes work on both hostnames
- ✅ Mobile responsive
- ✅ Rotating placeholder cycles 4 examples

**Next:** Session 9g — Scraper Infrastructure (performance + geo correctness). Sessions 9f-followup (portal polish) and 9h (Claude Haiku integration) are parallel tracks, can happen anytime.

### Session 9d-1 (May 11-12, 2026) — City Expansion Phase 1 + Carrefour + Verification System

**Done:**
- **New chain shipped: Carrefour Israel** (chain_id `7290055700007`, operated by Global Retail C.I. — includes Carrefour + Mega + Yenot Bitan sub-brands under one publisher).
- **New portal type abstracted**: `scraper/publishprice.py` base class (~130 lines) for JS-embedded file listing portals. `scraper/carrefour.py` is a 6-line subclass. Reusable for future chains.
- **City expansion Phase 1**: added 5 new cities (Tel Aviv, Haifa, Be'er Sheva, Rishon LeZion, Ashdod) on top of existing Jerusalem + Bnei Brak. Total: 7 cities.
- **Store selection rule documented**: lowest 2 `store_id` integers per (chain_id, city) from chain's `stores` table. Deterministic, reproducible. Falls back to store_name pattern matching for chains with NULL city data (Victory, Yochananof, Keshet — pre-existing 8a issue).
- **Verification-before-scrape system (Path C)**: new `scraper/active_stores.yaml` populated by per-store `verify_publishes_pricefull()` check. `scraper/scheduled_stores.yaml` retained as intent/wish-list. `scraper/cron_main.py` reads from active_stores. **58 of 72 stores verified.** 14 excluded breakdown:
  - 11 Shufersal (mostly Sheli format — old Jerusalem stores without per-store PriceFull files; 1 Universe-format unknown; 1 BE-format not found in scan; 1 store missing from local DB)
  - 1 Rami Levy 004 (warehouse, no city)
  - 2 Osher Ad 002, 004 (warehouses, no city)
- **Verification report**: `db/verification_report_9d1.md` documents excluded stores by category for 9e replacement work.
- **Shufersal page-limit patch**: scraper's hardcoded `start_page + 25` cutoff replaced with "scan until all requested stores found, OR safety cap at 200 pages with logged not-found list."
- **Procfile fix**: added `cron: python -m scraper.cron_main` process type so Railway commands are repo-authoritative, not UI-only. Root cause of weeks of OFF-enrichment-instead-of-price-scrape silent failure.
- **Sample Promo XML captured** for future promotions session: `Promo7290661400001-250-202605112159-001.xml.gz` and `Price7290055700007-3210-202605112200.gz` saved as reference samples.

**Decisions made:**
- **Carrefour publisher returns Mega + Yenot Bitan stores too — take them all under "קרפור" display name.** Cleaner UX than trying to split.
- **Bnei Brak zero-Carrefour-stores is real**, not a CITY_CODES dict gap — verified via carrefour.co.il store locator manually.
- **Store_name inference approved** for Victory/Yochananof/Keshet city assignment when `stores.city` is NULL. YAML entries get a "city inferred from store_name" comment for future audit.
- **Keshet Haifa includes Hadar (real Haifa neighborhood) but EXCLUDES Nesher (separate municipality)** — sets a precedent: when sub-city names are ambiguous, prefer narrow interpretation over wide.
- **Path C (verification gate) chosen over Path A (Shufersal-specific patch)** — surfaces heterogeneity across all chains at once; sets architecture for 9e Registry work.
- **Sub-chain heterogeneity ("Yesh" = Shufersal haredi, "Mega" = Carrefour publisher) is a class of problem, not chain-specific.** Solving via systemic StoreNext-based registry (9e) rather than per-chain patches.
- **9g (Scraper Infrastructure) prioritized AHEAD of 9e (StoreNext Registry)** — performance + geographic correctness unblocks all subsequent sessions; registry's payoff is architecturally cleaner selection but doesn't unblock anything urgent.

**Files changed:**
- New: `scraper/publishprice.py`, `scraper/carrefour.py`, `scraper/active_stores.yaml`, `db/verification_report_9d1.md`
- Modified: `scraper/registry.py` (added Carrefour), `scraper/scheduled_stores.yaml` (added 46 new-city entries), `scraper/shufersal.py` (page-limit patch), `scraper/cron_main.py` (read from active_stores.yaml), `Procfile` (added cron: line)

**Bugs encountered & resolved:**
1. ✅ **Shufersal `start_page + 25` silent cutoff** — page-limit on `build_pricefull_index` was hiding the real issue (Sheli-format heterogeneity). Patched to 200-page safety cap with explicit not-found logging.
2. ✅ **Phase B "lowest 2 store_ids" selection picked stores that don't publish PriceFull** — primarily affected Shufersal (11 of 12 new-city stores excluded). Path C verification gate now catches this before runtime.
3. ✅ **Procfile missing `cron:` process type** — scraper-cron service was silently running `python -m scraper.fetch_off` from Railway UI config, not the actual price scrape. Last successful price load before fix was April 25 (16 days stale). Production prices were intact but not refreshing. Caught by reviewing build logs after first 9d-1 cron run "succeeded" in ~5 min instead of expected 15-25 min.
4. ⚠️ **Geo-blocking on Victory + Carrefour** — both `laibcatalog.co.il` (Victory) and `prices.carrefour.co.il` (Carrefour) reject Railway US-West IPs. Confirmed via VPN test (works from Israeli IP, fails from US/India). Other 5 chains' portals don't enforce this. **Status at session close: trying Railway EU-West region as zero-cost mitigation; if insufficient, Israeli VPS migration planned in 9g.**

**Outcome:**
- ✅ Carrefour scraper shipped and verified locally (153 stores in StoresFull catalog, 130 city-mapped, 23 NULL-city for cities not in CITY_CODES dict)
- ✅ Verification system shipped — 58/72 store gate working as designed
- ✅ Procfile bug fixed, repo now source of truth
- ✅ 5 of 7 chains successfully loaded fresh prices to production: Shufersal, Rami Levy, Osher Ad, Yochananof, Keshet (Carrefour + Victory blocked pending 9g geo fix)
- ✅ Production state at session close: 7 chains, 49 stores, 372,159 prices (5 chains with fresh data from 5/11 evening; Carrefour + Victory pending 9g geo-fix). EU-West region experiment failed — caused 30× slowdown on Cerberus chains and didn't bypass geo-block. Reverted to US-West.
- 📝 New session 9g queued for infrastructure work; 9e (StoreNext Registry) queued behind it
- 📝 New session 9f queued for portal page (parallel track)
- 📝 CITY_CODES audit added as small follow-up patch session

**Next:** Session 9g — Scraper Infrastructure (performance + geographic correctness). Priority over 9e because (a) bulk inserts + parallelism unblocks all future city expansions, and (b) Victory + Carrefour need a geographic fix to get fresh data. StoreNext investigation continues in parallel; if their paid tier offers product catalog, 9e may re-prioritize ahead of 9g.

### Session 9g (May 17, 2026) — Scraper Performance + Kamatera Migration

**Scope at session start:** Three workstreams — (1) bulk inserts replacing per-row INSERTs, (2) parallel chain execution, (3) geographic fix for Victory/Carrefour geo-block. Chose order: bulk inserts → parallel → geo fix.

**What actually happened (order shifted by reality):**

**9g-1: Bulk inserts** — Implemented as batched `INSERT ... VALUES (...), (...)` at 1000 rows/statement across items, item_chain_names, prices tables. Local SQLite tests passed (5.8s per store, 15× speedup over baseline). First Railway production run crashed with Postgres `CardinalityViolation: ON CONFLICT DO UPDATE command cannot affect row a second time` — Rami Levy's source XML had 9 duplicate item_codes per store with identical prices. SQLite tolerated this silently; Postgres did not.

Dedup hotfix: deduplicate by `item_code` once per store before all three bulk calls in `scraper/base.py`. Last-wins semantics matches existing ON CONFLICT DO UPDATE. Added warning log for the rare case where duplicates have *differing* values (genuine data quality signal). Commit `4678207`. Local SQLite + Postgres-via-Docker validation passed.

**Railway Postgres disk-full crash** — Second Railway production attempt failed differently: scraper couldn't even connect because Postgres was in a crash loop. Root cause: Railway free trial 0.5 GB volume exhausted by accumulated WAL from previous failed runs. Postgres logs showed `FATAL: could not write to file "pg_wal/xlogtemp.33": No space left on device` looping. Investigated Railway dashboard — trial status was "6 days or $2.45 left", no easy fix without paid tier upgrade.

**Decision: skip Path C "Railway Hobby probation" and go directly to Path B "all-in on Kamatera."** Reasoning: Railway's tier curve doesn't fit a data-ingestion workload; we'd outgrow Hobby's 5GB in ~3 months anyway. GCP free tier rejected after fact-check (Always-Free e2-micro is US-only, doesn't solve geo-block). Kamatera chosen: Tel Aviv DC, 30-day free trial, ~$17/mo for 1 vCPU / 2 GB RAM / 30 GB SSD, simple operational model.

**Kamatera migration (Phases 2-6):**
- Provisioned `scrp-prod-il` at `185.229.226.190` (Tel Aviv, Type B General, Ubuntu 24.04 LTS)
- Server hardening: non-root `dude` user with sudo, SSH key auth, password SSH disabled, UFW firewall (22 + 5432), fail2ban, timezone Asia/Jerusalem
- Postgres 18.4 from PGDG official repo (not Ubuntu's default), tuned for 2GB RAM (shared_buffers 512MB, effective_cache_size 1GB, work_mem 16MB, wal_compression on)
- Database `xxl_super` owned by `scrp_app` user (password generated via `openssl rand -base64 32`, stored in password manager)
- Scrp repo cloned to `/home/dude/scrp`, venv created, requirements installed, `.env` at `~/scrp/.env` with permissions 600
- All 9 expected tables created (chains, stores, items, item_chain_names, prices, favorites, fetch_runs, saved_baskets, users)
- systemd timer `scrp-cron.timer` scheduled daily 03:00 IDT (DST-aware via OnCalendar). Service exits inactive on success; `Restart=no` so failures are visible.

**Validation results — the moment of truth:**

Three-chain geo-block test:
| Chain | Store | Prices | Time | Result |
|---|---|---|---|---|
| Victory | 008 | 4,684 | 4.2s | ✅ Geo-block resolved |
| Carrefour | 6 | 3,943 | 3.0s | ✅ Geo-block resolved |
| Shufersal | 073 | 4,823 | 40.3s | ✅ (page-scan bottleneck unrelated to geo) |

Full cron run, 7 chains × 58 stores:
| Chain | Stores | Prices | Time |
|---|---|---|---|
| Shufersal | 1/1 | 4,823 | 41s |
| Rami Levy | 14/14 | 101,620 | 39s |
| Osher Ad | 8/8 | 57,713 | 24s |
| Victory | 9/9 | 74,675 | 29s |
| Yochananof | 9/9 | 62,666 | 25s |
| Keshet | 8/8 | 96,301 | 35s |
| Carrefour | 9/9 | 33,392 | 15s |
| **Total** | **58 stores** | **430,190 prices** | **3m 31s** |

Exit code 0, no errors. Keshet logged 2 stores with duplicate item_codes having differing values (dedup last-wins applied, warning logged — working as designed).

**Decisions made:**
- **All-in on Kamatera (Path B) over Path C "Railway Hobby probation"** — sunk-cost-fallacy avoidance; Railway tier curve wrong for our shape regardless of immediate fix
- **GCP free tier rejected** — Always-Free e2-micro is US-only (wrong region, geo-block remains); $300 credit burns in ~4 weeks under real load; complexity tax not worth saving $4/mo
- **9g-2 (parallel chains) deferred indefinitely** — sequential is 3m31s; parallelism saves ~2.8 min; low ROI vs other levers
- **Shufersal page-scan caching identified as higher-leverage future optimization** than parallelism — would drop full cron from 3m31s to ~1m
- **Postgres tuning explicitly captured in postgresql.conf** rather than left at defaults — 2GB RAM box needs hand-tuning to perform well

**Files changed:**
- `scraper/base.py` — added `valid_deduped = list({item['item_code']: item for item in valid}.values())` dedup before bulk insert calls + warning log for differing-value duplicates
- `db/db.py` — bulk insert functions for items, item_chain_names, prices (batched VALUES at 1000 rows/statement)
- Server-side new files (not in git, on Kamatera only):
  - `/etc/systemd/system/scrp-cron.service` — runs `cron_main` as `dude` user, sources `.env`
  - `/etc/systemd/system/scrp-cron.timer` — daily 03:00 IDT, DST-aware
  - `/etc/postgresql/18/main/postgresql.conf` — tuned for 2GB RAM
  - `/etc/postgresql/18/main/pg_hba.conf` — temporary `0.0.0.0/0` for scrp_app (to be narrowed in Phase 7)
  - `/home/dude/scrp/.env` — DATABASE_URL with localhost Postgres connection

**Bugs encountered & resolved:**
1. ✅ Postgres CardinalityViolation on ON CONFLICT — duplicate item_codes in source XML, fixed via dedup in base.py (commit 4678207)
2. ✅ SQLite vs Postgres semantic mismatch — SQLite tolerates ON CONFLICT duplicates in a single statement, Postgres rejects. Local SQLite tests were insufficient. Going forward, Docker Postgres test recommended for any DB-touching code change.
3. ✅ Railway Postgres disk-full → crash loop — accepted data loss (reproducible from gov.il), migrated to Kamatera with proper disk sizing (30 GB vs 0.5 GB)
4. ⚠️ CC's automated SSH password auth failed on Kamatera even though manual SSH worked — root cause unclear (possibly special chars in password or rate limiting). Worked around by manually installing SSH key on server, then having CC use key-based auth thereafter. **Note for future sessions**: use SSH key auth from day 1, don't fight password auth through CC's transport layer.

**Outcome:**
- ✅ Scraper migrated end-to-end to Kamatera Tel Aviv
- ✅ Geo-block resolved (all 7 chains working)
- ✅ 25× performance improvement (90 min → 3m31s)
- ✅ Postgres on same host as scraper = localhost writes, no network latency for bulk inserts
- ✅ systemd cron scheduled daily 03:00 IDT
- ✅ Server hardened (key-only SSH, UFW, fail2ban)
- ⏸️ Phase 7 (frontend reroute) deferred to next session — touches live site, better with fresh focus
- ⏸️ Phase 9 (backups) deferred — important but not urgent
- 📝 super.xxl.co.il is currently broken until Phase 7 lands. Acceptable: it was already broken from Railway Postgres crash, so this isn't new user-facing breakage.

**Cost summary:**
- Kamatera: $0 (in 30-day free trial, ~$17/mo after Jun 17, 2026)
- Railway: ~$2.45 trial credit remaining, will expire ~May 23, 2026 — let it lapse naturally rather than actively cancel (web service still needed until Phase 7 completes)
- Net cost: $0 this month, $17/mo from Jun onwards (vs estimated $25+/mo if we'd stayed on Railway Hobby + paid for bigger volume)

**Credentials added to password manager this session:**
- `scrp-prod-il root` (Kamatera root user)
- `scrp-prod-il dude` (sudo user, daily driver)
- `scrp_app Postgres password` (used in DATABASE_URL — will go into Railway web env var in Phase 7)

**Next:** Session 9g Phase 7 — Reroute Railway web service `DATABASE_URL` env var to point at Kamatera Postgres (`185.229.226.190:5432/xxl_super`). Pre-work: identify Railway's egress IP to narrow `pg_hba.conf` from temporary `0.0.0.0/0`. Risk: touches live site, do with fresh focus. After Phase 7, super.xxl.co.il is healthy again. Then Phase 9 (pg_dump backups + Backblaze B2 offsite).

### Session 9n (May 25, 2026) — 3-Chain Diagnostic + Cron Timing Fix + FreshnessStrip Deploy

**Goal:** Diagnose why Victory, Osher Ad, and Carrefour consistently loaded 0 files on daily cron; fix root cause; two follow-ups from catch-up run.

**Root cause — confirmed timing race:**
Cron fired at 03:00 IDT = midnight UTC. All three failing portals publish PriceFull files AFTER midnight UTC:
- Carrefour (publishprice.py): publishes ~02:09 UTC daily (consistent over 6+ days)
- Osher Ad (Cerberus): publishes ~03:00–04:00 UTC
- Victory (laibcatalog.co.il): publishes ~04:00–05:00 UTC

Scraper arrived before the files existed → zero loads → but skipped stores **kept old prices** (snapshot fallback is implicit in `base.py`: `DELETE FROM prices WHERE store_fk=:store_fk` only runs when a store has an index entry; skipped stores untouched). Prices were stale but not gone.

**Fix — cron moved to 10:00 IDT (07:00 UTC):**
```bash
sed -i 's/OnCalendar=\*-\*-\* 03:00:00/OnCalendar=*-*-* 10:00:00/' /etc/systemd/system/scrp-cron.timer
systemctl daemon-reload
systemctl list-timers scrp-cron.timer
```
`Persistent=true` in the timer caused an immediate catch-up run on `daemon-reload` since the 10:00 IDT window was already past for the day.

**Catch-up run results — all 7 chains loaded successfully.**

**FreshnessStrip downward-expand:**
- Code in `web/src/components/FreshnessStrip.tsx` was already correct (document-flow expand with `mt-1` on `<ul>`, no absolute positioning). The upward-expand behavior on the live site was because the old build was never redeployed after the fix was committed.
- `web/deploy.zip` rebuilt locally at `C:\scrp\web\deploy.zip` (10.6 MB).
- **Pending Eltzur action:** Upload `C:\scrp\web\deploy.zip` to Hostinger File Manager → `public_html/super.xxl.co.il/` → Extract. This will also ship the alphabetical city sort and any other commits since the last Hostinger deploy.

**Column misalignment (fetch_runs table):**
Diagnosed as RTL terminal rendering artifact. Raw DB query confirmed: `files_attempted=1`, `files_loaded=1`, `items_inserted=4864` for Shufersal — correct. The reporter's table appeared column-shifted only because RTL layout reversed column order in the terminal viewer. No DB data issue.

**Decisions made:**
- **10:00 IDT chosen over 06:00 or 08:00** — 07:00 UTC gives 2+ hours of margin past Carrefour's 02:09 UTC publish and 1+ hour past Victory's ~05:00 UTC worst case. No meaningful operational downside (prices still updated same calendar day).
- **Cron description in `.timer` file NOT updated** (still says "3am Israel time") — low priority, timer behavior is authoritative; comment updated only in handoff.
- **Carrefour store-ID mismatch NOT fixed in this session** — Carrefour published files for stores the scraper didn't have registered (non-zero `files_attempted` but zero or few matched stores). Logged as open investigation for 9d-2.

**Files changed:**
- Server-side only: `/etc/systemd/system/scrp-cron.timer` — `OnCalendar` changed `03:00:00` → `10:00:00`
- `web/deploy.zip` — rebuilt locally (not committed; Hostinger deploy pending)

**Known issue surfaced in 9n scoping:**
Per-chain freshness (`/freshness` endpoint + FreshnessStrip) reads `MAX(run_at)` per chain — one fresh store makes the whole chain show "updated today." The 9d-2 scoping report found this masks per-store staleness (Keshet 50%, Yochananof 88% on May 25 despite all chains appearing green). A per-store freshness view is Priority 1 of 9d-2.

**Open items carried forward:**
- Hostinger upload of `web/deploy.zip` (FreshnessStrip fix goes live on upload)
- Carrefour store-ID mismatch: may be metric artifact — confirm with per-store metric first
- 9d-2 scoping report saved at `db/scoping_report_9d2.md`

### Session 9d-4 (May 28, 2026) — King Store (bina-projects) + Supabase Keep-alive Fix

### ⚠️ SEVERE — RTL IS NEVER A BUG. STOP FLAGGING IT.
Across multiple sessions the chat assistant has repeatedly raised false
alarms that Hebrew strings are "reversed/corrupted" in code, yaml, DB
names, or repr() output. EVERY instance has been a false positive — a
terminal/paste RTL rendering artifact, never a real data bug. Hebrew in
repr/screenshots/pasted output frequently APPEARS reversed; the underlying
bytes are correct. Do NOT flag reversed/corrupted Hebrew as a bug or
suspected bug. Do NOT propose codepoint rebuilds, byte checks, or
"just to be safe" verifications. If a string parses and the app runs, it
is correct. Address ONLY if a genuine reversed-text problem is seen in
PRODUCTION on the live site. (This wasted real time in 9d-4.)

**King Store — LIVE (9th chain)**
- chain_id 7290058108879 (confirmed live from filenames; the old 9j scar
  mislabeling this as Rami Levy is RESOLVED — it is genuinely King Store's).
- Coverage: Arab-sector + northern/mixed towns no other chain has.
- Production Postgres: 28 publishing stores, 148,016 prices, all cities
  resolved (050 אינטרנט intentionally NULL). Rides daily cron (in both
  active_stores.yaml and scheduled_stores.yaml; cron reads active as CONFIG).
- 31 stores in yaml; 338 (small village) deliberately excluded.

**bina-projects — REUSABLE BASE CLASS (the real prize)**
- scraper/binaprojects.py — BinaProjectsScraper(ChainScraper). Several other
  chains use this portal platform; adding one = ~4-line subclass (BASE_URL,
  CHAIN_NAME, CHAIN_ID). See scraper/kingstore.py.
- 3 JSON endpoints, all POST:
  - {BASE}/Select_Store.aspx (empty) -> [{"Kod","Nm"}]
  - {BASE}/MainIO_Hok.aspx (form WStore="",WDate="",WFileType="4") -> file
    list. WFileType: 0=all 1=stores 2=prices 3=promos 4=PriceFull 5=PromoFull.
    Returns FULL HISTORY (~1000 files); order unreliable.
  - {BASE}/Download.aspx?FileNm=<name> (empty) -> [{"SPath":"<gz url>"}] (LIST, take [0])
- Newest-per-store: select by the 12-digit YYYYMMDDHHMM stamp in FileNm, NOT
  the DateFile display string (display doesn't sort across days).
- KEY GOTCHA: bina files are ZIP (magic b'PK'), NOT gzip, despite .gz name.
  binaprojects._decompress overrides base to detect magic bytes; base.py
  untouched (other chains still gzip).

**Supabase keep-alive — FIXED**
- Old ping hit /auth/v1/health → 200 without touching Postgres → never
  counted as activity; project paused despite daily "ping OK" logs.
- Now reads 1 row from public.keepalive via /rest/v1/ (real DB read);
  success requires non-empty body. New table public.keepalive (1 dummy row,
  anon SELECT via RLS + explicit grant, future-proof for Oct 30 Data API
  change). No .env change. Rides daily cron. Verified: "DB read confirmed."

**Tooling added**
- scripts/run_one.py — standalone single-chain runner:
  `python -m scripts.run_one <chain_id> [--yaml active|scheduled]`. Mirrors
  cron_main setup; no cron logic / no Supabase ping / one chain. DATABASE_URL
  unset = local sqlite (safe); set from systemd env = Postgres.

**KNOWN ISSUES / DEFERRED**
- SCHEMA DRIFT: fetch_store_runs exists ONLY in Postgres migration
  9d2_fetch_store_runs.sql, never added to schema.sql → local sqlite on any
  machine lacks it; init_db won't create it. Fix: add it (+ fetch_runs/views)
  to schema.sql. Worked around manually on Kamatera prices.db in 9d-4.
- King Store load_stores inserts ALL portal stores (33), not just yaml's 31
  → store rows 000 and 338 exist with no prices (harmless empties). Add a
  target filter to load_stores if the table should match the yaml exactly.
- New cities (אום אל פחם, פוריידיס, כפר קאסם, רהט) set via override but not in
  CITY_VARIANTS — filtering works, but won't alias-group with other chains'
  spellings. Future consolidation.
- 2x .env backups (.env.save, .env.save.1) untracked in repo root — contain
  secrets. Clean up; confirm .gitignore covers .env*.
- VM "System restart required" — reboot in a maintenance window.

**Commits (9d-4)**
ea03cf5 Supabase cron fix · 71a335a bina base + KingStore + registry ·
917c555 store lists · 70218d7 ZIP-not-gzip fix · 3304062 NULL-city overrides ·
2c3d531 run_one.py · cfaa942 King Store city overrides (8 branches)

---

## Session 9d-7 (June 1 2026) — StoresFull XML ingestion + cron fixes

### Commits
- a6c2edb: scripts/ingest_store_xml.py — StoresFull XML city ingestion script (dry-run safe, --apply to write)
- fddc113: fix — never overwrite good city_norm with NULL (safety guard)
- 2533161: fix — קרית/קריית variants for missing canonicals (קריית מוצקין, קריית שמונה, קריית אתא)
- d0b0129: fix(ui) — enable chain filter in compare mode

### Data fixes applied
- 244 city_norm rows updated from StoresFull XMLs across Shufersal, Victory, Carrefour, King Store, Rami Levy, Keshet, Tiv Taam
- תל אביב consolidated from 3 entries → 1 (90 stores)
- NULL city_norm: down to 23 (all intentional — online/phantom stores)
- קשת טעמים name fix in chains table

### Infrastructure fixes
- systemd TimeoutStopSec + TimeoutStartSec set to infinity (cron was being killed by 1min30s timeout)
- Added 2G swap (/swapfile2) — total swap now 4G, persisted in /etc/fstab
- Root cause of OOM kill: Shufersal 320-store scrape peaks at 1.6G RAM + 933M swap. Fix: more swap for now; delta files as long-term solution

### Cron status
- Ran successfully May 30 (429 stores, 2.45M prices, 11 chains)
- Killed twice June 1 — first by timeout, then by OOM during Shufersal 320-store scrape
- Third attempt running now with timeout=infinity + 4G swap

### 9d-8 priorities
1. Verify tonight's cron completes successfully
2. Promo files pipeline (t=2 files → DB → surface on site)
3. Hazi Hinam scraper (delta-aware, custom HTML parser)
4. Victory coverage check
5. Search quality — חלבי/חלב bleed
6. Bina wave 2 — זול ובגדול, סופר ספיר, סיטי צפרير and others from Store_XML unknowns
7. Delta files architecture (replace PriceFull with Price delta for high-store-count chains)

### Still deferred
- Carrefour non-publishers re-check
- fetch_store_runs schema.sql drift
- King Store load_stores target filter
- .env.save cleanup
- VM reboot (deferred again — cron running)
- Shefa coverage-calc fix
- GS1 scoping

### Additional items completed late session
- systemd timeout fix (infinity) + 2G swap added (/swapfile2, persisted in fstab)
- CLAUDE.md created (ead1a3f) — CC operating guide, replaces handoff paste at session start
- Cron ran successfully past store 326+ (previous kill point was 283) — swap fix confirmed working
- Cron still running at 15:05 on Paz chain (store 541/262) — architectural concern flagged
- Decision: switch to delta (Price) files for daily scraping in 9d-8

### City normalization — BROKEN, needs rebuild in 9d-8

Current state (June 1 2026 end of session):
- city_norm column has ~150+ distinct values, many wrong: neighborhoods treated as cities, duplicate spellings, obsolete names (נצרת עילית), non-existent places (כוכב הצפון, כורדני, עמק חפר, צומת גבעת מרדכי, צור יגאל, צור משה)
- Multiple manual SQL patches applied this session made things worse, not better
- Cron overwrites fixes every night since scrapers use normalize_city() which maps to our broken canonicals
- Root cause: no authoritative city reference — we've been patching reactively

What's needed (9d-8 Task 0 — before cron architecture work):
- Download Israel CBS official settlement list as authoritative reference
- Build city_canonical mapping table in DB (settlement_code → official_name)
- Add city_canonical column to stores table
- One-time migration: fuzzy-match all existing city_norm values to canonical list
- Update /cities API endpoint to use city_canonical
- Update cron to write city_canonical on each scrape
- Reference: Cheapersal uses "תל אביב - יפו" (238 stores, 28 chains) as canonical — confirms official CBS naming

9d-8 kickoff prompt: see below handoff.

### 9d-8 priorities (revised)
0. **City normalization rebuild** — see "City normalization — BROKEN" section above; must land before cron architecture work
1. Verify cron completed all 15 chains + new chains seeded correctly
2. Delta architecture: switch daily to Price delta + add PromoFull pipeline + chain parallelism
3. Bina wave 2: זול ובגדול, סופר ספיר, סיטי צפרير + others from Store_XML unknowns
4. Search quality: חלבי/חלב bleed fix
5. Hazi Hinam scraper (dedicated session — delta-aware, custom HTML)
6. Victory coverage check

---

## Session 9d-6 — CITY_VARIANTS cleanup + Shufersal sweep + 4 new chains + Kamatera frontend migration

### Commits
- 7fae88a: CITY_VARIANTS cleanup — 14 new canonicals, 5 variants added, 17 STORE_CITY_OVERRIDES
- cab4094: Shufersal full sweep — 25 → 320 stores (95 BE excluded, 2 wholesale excluded, 878 deleted from DB)
- add0932: 4 new Cerberus scrapers — Dor Alon/AM:PM (157), Paz/Alonit (262), Fresh Market (45), Super Yuda (26). Registry now 15 chains.
- 74f9880: scripts/deploy_frontend.ps1 — Kamatera frontend deploy script

### Infrastructure
- super.xxl.co.il frontend migrated from Hostinger to Kamatera (185.229.226.190)
- nginx static file server configured at /var/www/super.xxl.co.il/
- SSL cert issued via certbot (expires 2026-08-29, auto-renews)
- DNS A record updated at box.co.il: super.xxl.co.il → 185.229.226.190
- Hostinger remains active (2yr subscription paid) — available as cold backup for xxl.co.il portal
- Deploy process: run scripts/deploy_frontend.ps1 from repo root (builds + scps to Kamatera)

### Key decisions
- BE-branded Shufersal stores (95) excluded — pharmacy/beauty only, not groceries. Onboard as separate chain later.
- Dor Alon = AM:PM only (157 stores, IDs 401–992 + 901–905, 991–992)
- Paz = Alonit gas station stores (262 stores, EV charging nodes 891/4101/4102 excluded)
- Fresh Market (7290876100000) = federation of 7 sub-brands under one chain_id: Fresh Market, Machsanei Mazon, Machsanei Lahav, Hyper Dudu, Super Dush, Tip Tov, Chaviv
- סביון is an independent municipality, not part of Petah Tikva
- מודיעין עילית must NEVER be merged with מודיעין-מכבים-רעות — separate Haredi municipality

### Deferred / next session (9d-7) — priority order
1. Verify tonight's cron — confirm all 15 chains seed correctly, check city_norm NULLs on new chains (Paz especially)
2. Hazi Hinam scraper — custom HTML parser, Azure Blob, delta files (NOT PriceFull for most stores). Chain ID: 7290700100008. 12 physical stores (201–219), store 103 = delivery exclude. Price page: https://shop.hazi-hinam.co.il/Prices
3. Victory coverage check — already in registry, check current store count vs available
4. StoresFull XML ingestion — every chain publishes a StoresFull XML alongside price files. Should use as ground truth for store metadata instead of manual STORE_CITY_OVERRIDES. Strategic item.
5. Promo files pipeline — t=2 on Cerberus/price pages returns promotional files. Add to DB and surface on site.
6. Multi-select city + chain dropdowns — UI feature, add בחירה מרובה to both dropdowns
7. Search quality — חלבי/חלב bleed (tokenization fix)
8. Bina wave 2 — זול ובגדול, מעיין 2000 and others (lower priority)

### Still deferred (lower priority)
- Carrefour non-publishers re-check
- fetch_store_runs schema.sql drift
- King Store load_stores target filter
- .env.save cleanup
- VM reboot
- Shefa coverage-calc fix
- GS1 scoping (separate workstream)
- DNS TTL: lower _railway-verify TXT record TTL from 7200 → 600 (cosmetic)

---

### Session 9d-5 — Shefa Birkat Hashem + Shuk Hayir onboarding (2026-05-28)

**Scope pivot:** Session opened with Paz + Dor Alon brand-filtering as the
locked priority. Eltzur surfaced two bina-projects portals (Shuk Hayir +
Shefa Birkat Hashem) that were structurally identical to King Store (9d-4),
so scope shifted to the cheaper, mechanical onboarding. Paz + Dor Alon
deferred to a dedicated brand-filtering session.

**Delivered:**

- Two new chains live in production Postgres:
  - **שפע ברכת השם** (chain_id 7290058134977) — 30 stores configured, 22
    publishing PriceFull. Haredi-sector coverage: Beitar Ilit (8 stores),
    Jerusalem (10), Beit Shemesh (3), Modi'in Ilit (2), Bnei Brak (2),
    plus Givat Ze'ev, Elad, Tel Tzion, Netivot, Ofakim, Ashdod, Afula.
    Items: 59,971. Coverage on /coverage: 73.3% (8 in-dropdown stores
    don't publish PriceFull — kept in yaml for future-pickup).
  - **שוק העיר** (chain_id 7290058148776) — 20 stores configured, 19
    publishing. Mixed mainstream coverage: Ashkelon, Ashdod, Kiryat Gat,
    Kfar Saba, Bnei Brak, Ramla, Holon, Timorim, Efrat, Netivot, Or
    Akiva, Ra'anana, Hadera, Jerusalem. Store 304 = online fulfillment
    hub (Ramot); 10 online duplicates (305, 307, 309, 311-314, 318, 319,
    322) deliberately excluded. Items: 81,586. Coverage: 95.0%
    (store 007 לב אשדוד intermittent).

- Files added/modified (commit 44441b6):
  - `scraper/shefabirkat.py` — new, 4-line subclass
  - `scraper/shukhayir.py` — new, 4-line subclass
  - `scraper/registry.py` — 2 imports + 2 SCRAPERS entries
  - `scraper/active_stores.yaml` + `scraper/scheduled_stores.yaml` —
    2 new chain blocks (30 + 20 store_ids each, identical in both files)
  - `scraper/city_names.py` — 50 STORE_CITY_OVERRIDES entries (30 Shefa
    + 20 Shuk Hayir), all hand-curated from chain branch lists provided
    by Eltzur in `city_list_shefa_and_shuk_hayir.xlsx`

- Production Postgres seeded via `scripts/run_one.py` against both chains
  before commit (DATABASE_URL exported from `/home/dude/scrp/.env` —
  systemd service uses EnvironmentFile=, not Environment=).
- /coverage endpoint verified showing 11 chains, 242 stores configured,
  229 loading 72h.
- Frontend live smoke test: both chains appear in city dropdown, in price
  comparison cards, in the all-chains count ("מחפש ב-11 רשתות").

**Confirmed working patterns from 9d-4 (reusable for future bina chains):**

1. BinaProjectsScraper base class is stable across 3 chains now (King
   Store, Shefa, Shuk Hayir). Future bina onboardings = ~4 line subclass
   + yaml block + STORE_CITY_OVERRIDES entries.
2. ZIP-not-gzip magic-byte detection in `_decompress` handled all 3
   chains correctly without modification.
3. The "stores in dropdown but not in Stores XML" pattern is normal for
   bina chains (King Store: 2, Shefa: 8) — they often publish PriceFull
   anyway, so keep them in the yaml.
4. `scripts/run_one.py` against local SQLite is the right pre-prod test;
   reusing `DATABASE_URL` from systemd env file is the right prod seed.

**Process learnings (added to operating notes):**

- **Cheapersal (https://cheapersal.co.il)** is a competitor reference site
  with full chain/branch/city coverage. Use as a market-spec for which
  chains exist, how brands are split (e.g., Cheapersal separates AM:PM
  from Alonit from Dor Alon — direct empirical answer to the Paz/Dor Alon
  brand-filtering question), and what chains we haven't onboarded yet.
  Add to general references; consult when scoping new chain waves.
- **CC compact-summary screen** is NOT tool output — it's CC summarizing
  its own context to itself when context fills up. If it appears,
  immediately start a fresh CC chat. Pattern recognition cue: it begins
  "● Compact summary" with a bulleted "Primary Request" / "Key Technical
  Concepts" structure.
- **PowerShell 5.1 `Set-Content -Encoding utf8` prepends a UTF-8 BOM**
  that lands as a stray  at the start of commit subjects. Cosmetic only,
  but for clean subjects use `Set-Content -Encoding utf8NoBOM` or
  `[System.IO.File]::WriteAllText($path, $msg, [System.Text.UTF8Encoding]::new($false))`.
  Do NOT amend + force-push to fix a BOM after the fact.
- **Modi'in Ilit ≠ Modi'in-Maccabim-Re'ut.** These are two different
  municipalities ~15km apart, with completely different demographics
  (Haredi vs secular/mixed). Eltzur initially requested merging them in
  CITY_VARIANTS; pushed back successfully. Same class of risk as the
  Pardes Hanna-Karkur split caught in 9d-2. Future-self warning: never
  merge cities sharing a name fragment without confirming they're the
  same municipality.

**Commit:** `44441b6` — "feat(scrapers): Shefa Birkat Hashem + Shuk Hayir
(bina-projects, chains 10 & 11)" (note: BOM artifact on subject line,
intentionally not amended).

---

### Session 9d-3 (May 27, 2026) — Shufersal Per-Store Fetch + Tiv Taam Chain

**Priority 4 — DONE (Shufersal page-scan eliminated, not just optimized):**

The original P4 task was "build a page-scan cache." A cache was already in
shufersal.py (undocumented). More importantly — the whole approach was
replaced. Eltzur noticed the Shufersal portal has a STORE DROPDOWN. DevTools
confirmed the selector posts a clean GET:
  GET /FileObject/UpdateCategory?catID=0&storeId={N}&sort=Time&sortdir=DESC
returns ONLY that store's files (~6-10 rows) as the same HTML table the
existing parser already handles. Same UpdateCategory endpoint the scraper
already used — nobody had tried the storeId param.

Shufersal now fetches per-store, one request per store, flat as the chain
grows — same shape as the other chains. No longer the weird one.

Changes (scraper/shufersal.py, commit 4c70a1d):
- build_pricefull_index rewritten: loops target store IDs, one _fetch_url per
  store via ?storeId=N. start_page param kept (ignored) for call-site compat.
- _fetch_url helper extracted; _fetch_raw_page is a one-line delegator
  (still used by load_stores).
- Newest PriceFull picked via max(pf_rows, key=filename). REVIEW CATCH:
  CC first used pf_rows[0] trusting server sort — server sorts the full
  mixed file listing, not the PriceFull subset, so [0] grabbed the STALE
  03:00 file instead of the 04:31 republish. Fixed to max().
- DELETED: the page-scan cache entirely — _CACHE_FILE, _load/_save_cached_
  start_page, _CACHE_MARGIN, _DEFAULT_START_PAGE, safety cap, page loop.
  .shufersal_cache.json on disk is dead, can be deleted manually.
- load_stores UNCHANGED — still page-walks for store name/city metadata.
  Folding into per-store path is a deferred follow-up.

Verification: 17/17 stores FOUND. 12 existing actives + 014/018 (verified
9d-2 deferred items, added to active_stores.yaml, commit 206a562) + spot-
check of 318 (אקספרס), 270 (BE), 035 (יוניברס) — all FOUND. The handoff's
old assumption that Shufersal sub-formats (אקספרס/BE/יוניברס) don't publish
PriceFull is WRONG across the board — they all publish.

**Priority 5 — DONE for Tiv Taam (deferred for others, see below):**

Probe of four candidate chains via published gov-portal credentials (Tiv Taam,
AM:PM/doralon, Fresh Market, King Store):
- Tiv Taam, AM:PM, Fresh Market: all Cerberus portal (url.publishedprices.co.il),
  username-only auth — ~5-line subclasses of CerberusScraper.
- King Store: bina-projects platform (kingstore.binaprojects.com) — separate
  portal, no scraper for it yet.

Tiv Taam SHIPPED (commit 6f234b4):
- chain_id 7290873255550, 46 retail stores (53 in Stores XML, minus 7 ליקוט
  warehouses: 502, 503, 512, 514, 515, 519, 523).
- scraper/tivtaam.py — 5-line subclass.
- scraper/registry.py — wired into the chain dictionary (this is where new
  chains get registered; pattern for future additions).
- active_stores.yaml + scheduled_stores.yaml — both updated.
- Verification: 46/46 PriceFull FOUND, 53/53 cities resolved, 0 NULLs.

CITY_CODES rebuilt from official sources (same commit):
- 12 new MOI codes added (104=מזרע, 346=גליל ים, 386=בני דרור, 587=סביון,
  1061=נצרת עילית, 1139=כרמיאל, 1167=קיסריה, 2100=טירת כרמל, 2530=באר יעקב,
  6800=קרית אתא, 8200=קרית מוצקין, 9400=יהוד).
- 7 spelling/name overrides applied from the authoritative Israel Post
  locality PDF in C:\scrp\data\ — typo fixes (3780 ביתר עלית→עילית; 171
  פרדסיה; 6400 הרצליה; 9100 נהריה) and official compound names (195
  קדימה→קדימה-צורן; 1200 מודיעין→מודיעין-מכבים-רעות; 5000 תל אביב→תל אביב-יפו).
- POLICY COMMENT added above CITY_CODES: NEVER include regional councils
  (מועצה אזורית) like נחל שורק. Only shopper-recognizable municipalities.
  Do NOT bulk-import locality.xls — it mixes cities and regional councils.

Locality file caveats discovered this session:
- C:\scrp\data\kod_yeshuvim_02.xls is the CBS internal serial code system,
  NOT the Ministry of Interior locality codes used by gov.il price portals.
  Different number space. DO NOT USE for CITY_CODES work.
- C:\scrp\data\locality.xls IS the correct MOI master, but labels code 31
  as "נחל שורק" (regional council) — the price portals use 31 for אופקים
  (the actual city). cerberus.py keeps the curated value 31=אופקים.
- Israel Post's סמל_ישוב_דואר_ישראל.pdf cross-confirms the MOI codes.

**Deferred queue (ranked by impact × readiness, top of list = next):**

1. **CITY_VARIANTS cleanup** — alias-mapping pass. All surfaced live by
   users in the city dropdown:
   a) זכרון / זכרון יעקב → canonical "זכרון יעקב" (from 9d-2)
   b) תל אביב / תל אביב יפו → canonical "תל אביב-יפו" (from 9d-5)
   c) מודיעין → canonical "מודיעין-מכבים-רעות" (from 9d-5)
   d) DO NOT merge מודיעין עילית — separate Haredi municipality (from 9d-5)
   e) Audit dropdown for other split cities while in there.
   Pure data work, zero scraper risk, immediate visible improvement.

2. **Search quality — "חלבי" bleed.** From session 9f: searching "חלב"
   returns "חלבי" (kosher dairy marker) results. Tokenization / stop-word
   fix. Affects every search on the live site.

3. **Bina-projects wave 2.** Base class validated 3×. Candidate chains
   from Cheapersal cross-reference: זול ובגדול, מעיין 2000, סופר ברקת,
   סופר יודה, פוליצר, סיטי מרקט, KT מרקט, יילו. Could batch 4-6 chains
   in one session.

4. **Shufersal 270-store sweep.** Currently tracking 14 of ~270 stores.
   `shufersal_branch_list.csv` already captured. Largest single-step
   coverage expansion available.

5. **Paz + Dor Alon brand-filtering session.** Both publish multiple
   brands under one chain_id. Cheapersal already separates these brands
   (AM:PM / אלונית / סופר אלונית for Dor Alon; freshmarket / סופר חביב
   / מחסני השוק variants for Paz) — use as empirical target. Operating
   policy A: fetch each brand's real branch list first.

**Lower-priority / housekeeping:**

- Shufersal load_stores consolidation
- Carrefour non-publishers re-check (store 6, 183, 191; Yochananof 073)
- fetch_store_runs schema.sql drift fix
- King Store load_stores target filter
- .env.save / .env.save.1 cleanup
- Kamatera VM reboot (System restart required)
- Shefa coverage-calc fix — distinguish "configured but chain doesn't
  publish PriceFull" from real misses, so /coverage doesn't penalize us
  for chain decisions outside our control (would lift Shefa from 73.3%
  to ~100% honestly)
- GS1 scoping (separate workstream)

**General references:**

- **Cheapersal** (https://cheapersal.co.il) — competitor site with full
  chain/branch/city/items coverage. Consult when scoping new chain waves
  or making brand-split decisions.

---

### Session 9d-2 (May 25, 2026) — Per-Store Coverage Metric [Priority 1 complete]

**Done — Priority 1 of 9d-2:**
- New table `fetch_store_runs` (per-store sibling to per-chain `fetch_runs`): one row per store per cron run, status enum loaded/no_file/error. Migration: `db/migrations/9d2_fetch_store_runs.sql` (includes scrp_app GRANTs — see lesson below).
- `scraper/base.py`: emits one fetch_store_runs row per store during the load loop; fetch_runs INSERT now uses RETURNING id to correlate. store_id padded via _pad_store_id for consistency with stores table.
- New view `v_store_coverage_72h` + `/coverage` API endpoint (`db/query.py` fetch_coverage, `api/routers/coverage.py`, `api/models.py`). Denominator is configured count from active_stores.yaml, so never-ran chains show 0% not invisible. Sorted worst-first.
- Seed run completed (option B): full manual cron, 7 chains, 192s, errors none.

**Key finding:** The scoping report's coverage alarms were price_update_date artifacts. Real per-store load coverage as of seed run: Carrefour 88.9% (8/9), all other 6 chains 100%. Keshet "50%" and Yochananof "88%" from the scoping baseline were stale-XML-date noise, not missing stores.

**Carried into Priority 3:** (1) Carrefour store 6 — in active_stores.yaml but published no PriceFull on the seed run; investigate. (2) Shufersal — 100% is meaningless at 1 store configured; needs expansion.

**Lesson — new tables need explicit GRANTs:** The seed run first failed with "permission denied for table fetch_store_runs" — the table was created as postgres superuser but the scraper connects as scrp_app. Any new table created via `sudo -u postgres psql` MUST include `GRANT ... TO scrp_app` (table + sequence + any views) in the same migration file, or it's invisible to the scraper.

### Session 9d-2 (May 26, 2026) — Per-Store Coverage Metric + City Expansion

**Priority 1 — DONE (per-store coverage metric):**
- New table fetch_store_runs (per-store sibling to per-chain fetch_runs): one row per store per cron run, status enum loaded/no_file/error. Migration db/migrations/9d2_fetch_store_runs.sql (includes scrp_app GRANTs).
- scraper/base.py emits one fetch_store_runs row per store; fetch_runs INSERT now uses RETURNING id. store_id padded via _pad_store_id.
- New view v_store_coverage_72h + /coverage API endpoint (db/query.py fetch_coverage, api/routers/coverage.py, api/models.py). Denominator = configured count from active_stores.yaml.
- Key finding: the scoping report's coverage alarms (Keshet 50%, Yochananof 88%, Carrefour 22%) were all price_update_date artifacts. Real per-store load coverage is healthy.
- Lesson: new tables created via `sudo -u postgres psql` MUST include GRANT ... TO scrp_app (table + sequence + views) in the same migration, or the scraper (connects as scrp_app) gets "permission denied".

**Priority 2 — DONE (city expansion, 9 new 100K+ cities):**
- 9 cities: Petah Tikva, Holon, Bnei Brak, Ashkelon, Rehovot, Bat Yam, Beit Shemesh, Herzliya, Modi'in.
- Built two analysis scripts: scripts/discover_p2_cities.py (catalog discovery, 3-bucket output) and scripts/verify_p2_candidates.py (PriceFull verification via build_pricefull_index).
- 60 candidates verified, 55 PASSED, added to active_stores.yaml. Store count: 58 → 113.
- Surprise finding: Shufersal יש חסד sub-format DOES publish PriceFull (Bnei Brak 219/295/611, Beit Shemesh 606 all verified PASS). The handoff's assumption that all sub-formats fail is wrong — at least יש חסד works.
- Rami Levy store 016 (Bnei Brak Ayalon branch): catalog store_name says "רמת גן" but address מבצע קדש 68 confirms Bnei Brak municipality. Comment added in active_stores.yaml — do not "correct" it.

**Priority 3 — bar already met:** Proof cron run (326s, errors none) → /coverage shows all 7 chains ≥90% on the 113-store denominator: Shufersal 100% (12/12, was 1 store), Rami Levy/Osher Ad/Victory/Yochananof/Keshet all 100%, Carrefour 95.5% (21/22).

**Deferred to future sessions:**
- Shufersal stores 014 (Ashkelon) + 018 (Holon): דיל-format, verification failed ONLY because the page-scan hit its 236-page safety cap — likely real. Re-verify with higher page cap during Priority 4 (Shufersal page-scan optimization).
- Carrefour non-publishers: store 6, plus 183 (Bat Yam) + 191 (Holon); Yochananof 073 (Holon) — NO_FILE on verify. Carrefour per-store intermittency; re-check on a later run.
- Shufersal שלי/אקספרס/BE/יוניברס sub-formats: NOT yet tested. Herzliya and Rehovot got zero Shufersal this session because they only have these formats. Worth a dedicated Shufersal sub-format session.
- Priority 4 (Shufersal page-scan cache) and Priority 5 (new chains) not started.

**New chains note:** User wants to choose chains rather than use the scoping report's AM:PM/Freshmarket/Co-op list. Candidates discussed: Tiv Taam (good), King Store (smaller, ~26 branches, unique Arab-sector coverage). Hazi Hinam stays deferred (HTML-scraped, fragile). Decide via portal-type probe at start of Priority 5.

**Cron timing — confirmed, do NOT change:** Daily cron stays 10:00 IDT. 9n moved it there because Osher Ad publishes ~07:00 IDT; earlier cron re-creates the 9n silent-failure bug. The FreshnessStrip is already real-time (reads /freshness live per page load) — it shows "yesterday" before ~10:05 simply because that day's scrape hasn't run yet. Possible future polish: strip copy noting "updates daily by 10:00" so early-morning visitors don't read it as stale.

**Operating note:** For ad-hoc DB queries with Hebrew or special characters, SSH in interactively first (ssh dude@..., then run the query at the server's bash prompt) — non-interactive ssh "..." from PowerShell mangles quotes and Hebrew.

**Note for future migrations:** CC tip — when a migration creates a table, always append the scrp_app grants to the same .sql file.

### Session 9d-2 (May 26, 2026) — Coverage Metric, City Expansion, Infra

**COMPLETED:**

Priority 1 — per-store coverage metric (DONE):
- New table fetch_store_runs (per-store, sibling to per-chain fetch_runs); status enum loaded/no_file/error. Migration db/migrations/9d2_fetch_store_runs.sql (includes scrp_app GRANTs).
- scraper/base.py emits one fetch_store_runs row per store; fetch_runs INSERT uses RETURNING id.
- New view v_store_coverage_72h + /coverage API endpoint. Denominator = configured count from active_stores.yaml.
- Finding: the scoping report's coverage alarms (Keshet 50%, Yochananof 88%, Carrefour 22%) were all price_update_date artifacts — real per-store coverage was healthy.

Priority 2 — city expansion (DONE):
- 9 new cities: Petah Tikva, Holon, Bnei Brak, Ashkelon, Rehovot, Bat Yam, Beit Shemesh, Herzliya, Modi'in.
- Scripts: scripts/discover_p2_cities.py (catalog discovery), scripts/verify_p2_candidates.py (PriceFull verification).
- 60 candidates verified, 55 PASSED, added to active_stores.yaml. Store count 58 → 113.
- Finding: Shufersal יש חסד sub-format DOES publish PriceFull (verified). The assumption that all Shufersal sub-formats fail is wrong for יש חסד.
- Rami Levy 016 = Bnei Brak Ayalon branch (catalog store_name says "רמת גן", address confirms Bnei Brak) — comment in active_stores.yaml, do not "correct".

Priority 3 — bar met: proof cron run, /coverage shows all 7 chains ≥90% on the 113-store denominator. Shufersal 100% (12/12, was 1), others 100%, Carrefour 95.5%.

City normalization (DONE): victory.py now normalizes city on store insert via resolve_city (Victory tagged branches "חולון קוגל" etc., creating duplicate dropdown cities). Permanent fix — confirmed working. scripts/normalize_store_cities.py exists as a one-time cleanup but was NOT needed and must NOT be run with --apply: its prefix-strip logic false-positives on hyphenated municipalities (פרדס חנה-כרכור, מודיעין-מכבים-רעות).

Supabase keep-alive (DONE): cron_main.py ping_supabase() pings Supabase /auth/v1/health each cron run to reset the 7-day free-tier inactivity timer. Confirmed "ping OK (200)". Server .env has SUPABASE_URL + SUPABASE_ANON_KEY. Note: /rest/v1/ returns 401 for anon key — must use /auth/v1/health.

Freshness strip (DONE): added static footnote "* עדכון מחירים מתבצע בשעות הצהריים" to the expanded FreshnessStrip, so early-morning visitors understand prices update midday.

**DEFERRED / NEXT SESSION:**
- Priority 4 — Shufersal page-scan optimization (page-scan cache). Includes re-verifying Shufersal stores 014 (Ashkelon) + 018 (Holon): דיל-format, failed verification ONLY due to the 236-page scan cap — likely real, re-verify with higher cap.
- Priority 5 — new chains. User wants to choose: Tiv Taam (good candidate), King Store (~26 branches, unique Arab-sector coverage). Hazi Hinam stays deferred (HTML-scraped). Decide via portal-type probe (verify against each chain's endpoint) before building.
- Shufersal שלי/אקספרס/BE/יוניברס sub-formats: not yet tested. Herzliya and Rehovot got zero Shufersal this session (only these formats). Worth a dedicated session.
- Carrefour non-publishers: store 6, 183 (Bat Yam), 191 (Holon); Yochananof 073 (Holon) — NO_FILE on verify, re-check later.
- CITY_VARIANTS cleanup: CITIES contains both "זכרון" and "זכרון יעקב". Make "זכרון יעקב" canonical, "זכרון" a variant in CITY_VARIANTS. Small. Check how CITIES and CITY_VARIANTS relate before editing — CITIES is used live by resolve_city.
- Lod/Ramla, Ramat Gan/Givatayim: possible user-facing city consolidation — separate product decision, own mapping table, not done.

**GS1 — incoming workstream (not started):**
GS1 Israel can license canonical item data: names, images, barcodes, nutrition, kosher, ingredients. ~₪6,000, affordable. This is the canonical product layer the project lacks (replaces abandoned OpenFoodFacts, parked StoreNext). GS1 constraint: some chains are not GS1 members; GS1 doesn't want non-members getting GS1 data via xxl as a backdoor. Working approach: per-chain gs1_eligible flag — ineligible chains stay listed for price comparison but show no GS1 enrichment. Frame to GS1 as a sales incentive (visible richness gap pushes non-members to join). Before signing: get the eligible-chain list explicit and in writing. Needs a dedicated scoping session.

**INFRA / SECURITY:**
- Rotate the scrp_app DB password — it was printed to terminal/chat this session. Not urgent (localhost-only DB) but should be done.

**OPERATING NOTES (important for all future sessions):**
- Terminal RTL display of Hebrew is EXPECTED and normal — it does not indicate a bug, no verification needed for display mangling. Only verify logic when a Hebrew string comparison is load-bearing (use repr() / JSON.stringify, or open the file in VS Code).
- CC cannot reliably surface file contents back to the operator — its file reads collapse ("Read 1 file / ctrl+o to expand") and don't paste through. Workaround: for any code review, the operator opens the file in VS Code and pastes it directly.
- PowerShell → ssh → bash quoting mangles Hebrew, special characters, and long strings (JWTs). For ad-hoc DB queries with Hebrew: SSH in interactively first, run the query at the server bash prompt. To get a file/credential onto the server: build it locally and scp it — never interpolate it into an ssh "..." command string.