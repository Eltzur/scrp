# SCRP — Project Handoff

> A living document. Update at the end of each session. Paste at the start of each new chat.
> Last updated: June 4, 2026 (end of session 9d-9 priority 1)

---

## 🎯 Current State

**Session 9d-9 priority 1 — COMPLETE.**

### What was done in 9d-9 (priority 1)

- **Delta Price file support** — shipped for 7 chains: Shufersal + Cerberus chains (Rami Levy, Osher Ad, Yochananof, Keshet, Fresh Market, Super Yuda). `DELTA_CHAINS` in `registry.py`. `build_price_index` added to `cerberus.py`.
- **Per-store ThreadPoolExecutor parallelism** — `STORE_WORKERS=4` in `base.py` and `shufersal.py`. `_process_store` / `_process_store_shufersal` each open their own DB connection and write `fetch_store_runs` immediately. `fetch_runs` inserted upfront (status=`running`), updated at end with final counts.
- **Generator exhaustion bug fixed** — `items = list(items)` added in `shufersal.py` before delta split.
- **`docs/portals.md`** — portal credentials and delta status for all 13 chains.

### Cron performance (post 9d-9 priority 1)

| Chain | Before | After | Speedup |
|---|---|---|---|
| Shufersal | 4436s | 544s | 8× |
| Tiv Taam | 6913s | 93s | 74× |
| Rami Levy | — | ~46s (26 stores) | — |
| Full cron | ~2.1h | target <30 min | TBC at 10:00 IDT |

Full cron result to be confirmed by tomorrow's 10:00 IDT run.

### What was done in 9d-8 (for reference)

- city_canonical rebuilt from CBS 2024 (1057 stores, 0 NULLs). city_canonical is now source of truth.
- Paz and Dor Alon removed (422 stores, 887K prices deleted).
- City dropdown reads from city_canonical, 0.13s response (was 3.7s).
- Chain-level parallelism: `cron_main.py` `ThreadPoolExecutor(max_workers=6)`.
- Supabase keep-alive timer files deployed to `deploy/systemd/` — still needs enable+start on server.

---

## 🏗️ Architecture

| Layer | Tech | Where | Status |
|---|---|---|---|
| Frontend | React + Vite + TypeScript + Tailwind | Kamatera nginx (`185.229.226.190`) — serves super.xxl.co.il | ✅ Live |
| Portal | Static HTML | Hostinger `public_html/` — serves xxl.co.il | ✅ Live |
| Backend | FastAPI + gunicorn + uvicorn | Kamatera via systemd `scrp-api.service`, behind nginx + Let's Encrypt | ✅ Live |
| Database | Postgres 18.4 | Kamatera `185.229.226.190`, localhost-only | ✅ Live |
| Scraper cron | Python (`scraper.cron_main`) | Kamatera via systemd `scrp-cron.timer` | ✅ Daily 10:00 IDT |
| Backups | pg_dump → rclone → Backblaze B2 | systemd `scrp-backup.timer` (daily 04:00 IDT) | ✅ Live |
| Supabase keep-alive | systemd `supabase-keepalive.timer` | Kamatera, every 4h | ⏳ Installed, needs enable+start |
| Auth | Supabase | Auth only — no Data API usage from client | ✅ Live |

**Repo:** github.com/Eltzur/scrp (main branch = production)

**Production URLs:**
- Portal: https://xxl.co.il
- Supermarket app: https://super.xxl.co.il
- Backend API: https://api-super.xxl.co.il
- SSH: `ssh dude@185.229.226.190`

---

## 📊 Current Production State (post 9d-9 priority 1)

- **13 chains** in registry (Paz and Dor Alon removed in 9d-8)
- **1057 stores** in active_stores.yaml, all with city_canonical populated (0 NULLs)
- **city_canonical** is the source of truth — API, dropdown, and filter queries all use it
- **City dropdown** response: ~0.13s (stores table only, no prices JOIN)
- **Shufersal**: 315/320 stores loading (5 stores with no PriceFull — upstream gap, not a bug)
- **Delta mode**: 7 chains active — Shufersal, Rami Levy, Osher Ad, Yochananof, Keshet, Fresh Market, Super Yuda
- **Cron runtime**: ~2.1h → target <30 min (per-store parallelism shipped, first full run pending)
- **Supabase keep-alive**: timer files deployed — still needs `enable + start` on server

---

## 🎯 Next Session: 9d-9 priority 2

**Goal:** Missing stores for existing chains.

**Pending from 9d-9 priority 1:**

1. **Confirm full cron run** — check 10:00 IDT tomorrow. Expected <30 min with per-store parallelism.
2. **Supabase keep-alive** — still needs enabling on server:
```bash
sudo systemctl daemon-reload
sudo systemctl enable supabase-keepalive.timer
sudo systemctl start supabase-keepalive.timer
```
3. **Delta for remaining chains** — Victory, King Store, Shefa, Shuk Hayir need `build_price_index` per portal type. Carrefour (portal was down 2026-06-04) — check when back up.

**Priority 2: missing stores for existing chains** (scope TBD at session start).

---

## 🏗️ Key Infrastructure Commands

```bash
# SSH
ssh dude@185.229.226.190

# API
sudo systemctl status scrp-api
sudo journalctl -u scrp-api -n 20 --no-pager

# Cron
sudo journalctl -u scrp-cron -n 20 --no-pager
sudo systemctl start scrp-cron.service  # manual run

# DB
sudo -u postgres psql xxl_super

# Manual scrape one chain
cd ~/scrp && source venv/bin/activate && source .env
python3 -m scripts.run_one <chain_id>

# Backup
sudo systemctl start scrp-backup.service
```

---

## 🗂️ Key File Locations

| File | Purpose |
|---|---|
| `scraper/registry.py` | Chain registry + `DELTA_CHAINS` (7 chains) + `uses_delta()` |
| `scraper/active_stores.yaml` | Verified stores for cron (1057 stores) |
| `scraper/cron_main.py` | Cron entry point — chain-level parallelism (max_workers=6) |
| `scraper/base.py` | `_process_store` + `STORE_WORKERS=4` per-store parallelism |
| `scraper/shufersal.py` | `_process_store_shufersal` + lazy delta URL fetch |
| `scraper/cerberus.py` | `build_price_index` for Cerberus delta files |
| `docs/portals.md` | Portal credentials and delta status for all 13 chains |
| `scraper/city_names.py` | CITY_VARIANTS, STORE_CITY_OVERRIDES (legacy — city_canonical is now authoritative) |
| `db/query.py` | All DB queries — city dropdown uses `fetch_cities()` (stores table only, no prices JOIN) |
| `api/routers/` | FastAPI routes |
| `scripts/apply_city_canonical.py` | Apply city_canonical CSV (UPDATE + DELETE actions) |
| `scripts/build_city_canonical.py` | Rebuild city_canonical from CBS data |
| `deploy/systemd/` | Systemd unit files (supabase-keepalive.service + .timer) |
| `web/src/App.tsx` | Top-level routing + city fetch on app mount (AppShell) |
| `web/src/components/Filters.tsx` | City/chain dropdown — receives cities as prop from HomePage |
| `scripts/deploy_frontend.ps1` | Frontend deploy to Kamatera |

---

## ⚠️ SEVERE Warnings (always apply)

- **RTL/Hebrew is NEVER a bug.** Hebrew in terminal/paste output often appears reversed — display artifact only. Never flag.
- **Railway is DEAD.** Project runs on Kamatera. Never reference Railway.
- **Never merge מודיעין עילית with מודיעין-מכבים-רעות** — separate municipalities.
- **Never merge BE-branded Shufersal stores into the main chain** — pharmacy/beauty only.
- **city_canonical is the source of truth** — do NOT use city_norm, do NOT patch CITY_VARIANTS for city display.

---

## 🔑 Key Architectural Decisions (standing)

- **city_canonical** rebuilt from CBS 2024 — authoritative. city_norm is legacy/broken, ignore it.
- **Kamatera consolidation** — all infra (Postgres + scraper + FastAPI + nginx) on single VPS at 185.229.226.190.
- **SQLAlchemy everywhere** — scrapers are DB-agnostic.
- **Snapshot pricing** — no history tracking yet.
- **Daily cron at 10:00 IDT (07:00 UTC)** — portals publish 02:00–05:00 UTC; 10:00 clears the window.
- **Verification-before-scrape** — `active_stores.yaml` is the gated list; `scheduled_stores.yaml` is the wish-list.
- **Freemium**: free tier is the honeypot. Only logged-out users see 25-item basket cap. Logged-in cap = 150.
- **Brand color**: emerald-600 (#059669).
- **Portal (xxl.co.il) vs supermarket app (super.xxl.co.il)** — hostname-based routing in React (`isPortalHostname()`).
- **Frontend deploy**: `.\scripts\deploy_frontend.ps1` from repo root.
- **Supabase is auth-only** — no Data API from client. User data lives in Kamatera Postgres.
