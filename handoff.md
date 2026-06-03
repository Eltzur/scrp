# SCRP — Project Handoff

> A living document. Update at the end of each session. Paste at the start of each new chat.
> Last updated: June 3, 2026 (end of session 9d-8)

---

## 🎯 Current State

**Session 9d-8 — COMPLETE.**

### What was done this session

- **Priority 1 DONE: city_canonical rebuild** — column rebuilt from CBS 2024 official settlement list. 1057 stores, 0 NULLs. city_canonical is now the source of truth for all city data (not city_norm).
- **Paz and Dor Alon removed** — both chains deleted from registry and active_stores.yaml. 422 stores and 887K prices deleted from DB.
- **City dropdown** now reads from city_canonical. Response time 0.13s (was 3.7s — prices JOIN removed). Fetch hoisted to app mount level (no per-open delay).
- **Supabase keep-alive timer installed** — systemd `supabase-keepalive.timer`, fires every 4h, pings `/rest/v1/stores` to keep Supabase connection warm. Files in `deploy/systemd/`.
- **Scripts in place for future rebuilds**: `scripts/apply_city_canonical.py` (UPDATE + DELETE actions from CSV), `scripts/build_city_canonical.py`.

### Priority 2 — NOT started, carry to 9d-9

- Cron parallel scraping — target <30 min for 1057 stores.
- Current cron is sequential; parallelism work deferred from this session.

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

## 📊 Current Production State (post 9d-8)

- **13 chains** in registry (Paz and Dor Alon removed in 9d-8)
- **1057 stores** in active_stores.yaml, all with city_canonical populated (0 NULLs)
- **city_canonical** is the source of truth — API, dropdown, and filter queries all use it
- **City dropdown** response: ~0.13s (stores table only, no prices JOIN)
- **Supabase keep-alive**: every 4h via systemd timer — files deployed, still needs `systemctl enable + start` on server
- **Cron runtime**: unknown for 1057 stores — sequential, needs parallelism work in 9d-9

---

## 🎯 Next Session: 9d-9

**Goal:** Cron parallel scraping, target <30 min for 1057 stores.

**Starting point:**
- `scraper/cron_main.py` — current sequential cron entry point
- `scraper/active_stores.yaml` — 1057 stores across 13 chains
- Measure actual current runtime first before parallelizing

**Supabase keep-alive — still needs enabling on server:**
```bash
sudo systemctl daemon-reload
sudo systemctl enable supabase-keepalive.timer
sudo systemctl start supabase-keepalive.timer
```

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
| `scraper/registry.py` | Chain registry (13 chains post 9d-8) |
| `scraper/active_stores.yaml` | Verified stores for cron (1057 stores) |
| `scraper/cron_main.py` | Cron entry point — target for 9d-9 parallelism |
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
