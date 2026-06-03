# XXL Scraper — Claude Code Operating Guide

## Project context
Israeli supermarket price comparison app. Backend: FastAPI + SQLAlchemy + Postgres on Kamatera VPS (185.229.226.190). Frontend: React/Vite served via nginx on same VM. Scrapers: Python, pulling from Israel's government price transparency XML feeds. GitHub: github.com/Eltzur/scrp.

## Operating rules (apply every session)
1. **Short responses** — status/diagnosis, options with recommendation, then commands. No mid-stream pivots.
2. **Fool-proof** — delegate to CC as much as possible. Prompts in copy-paste blocks. Minimize manual effort.
3. **Read context first** — always read handoff.md and recent chats before starting work.
4. **Read-and-report-STOP** — on any code change touching scrapers or city resolution, show findings and stop before writing fixes.
5. **One CC prompt per task** — batch all related changes into one prompt. No incremental back-and-forth on simple tasks.

## SEVERE warnings
- **RTL/Hebrew is NEVER a bug.** Hebrew in terminal/paste output often appears reversed — this is a display artifact, not a data bug. Never flag, never byte-check.
- **Railway is DEAD.** Project runs on Kamatera. Never reference Railway.
- **Never merge מודיעין עילית with מודיעין-מכבים-רעות** — separate municipalities.
- **Never merge BE-branded Shufersal stores into the main chain** — pharmacy/beauty only.

## City data — IMPORTANT
- **city_canonical is the source of truth** for all city data (rebuilt from CBS 2024 in 9d-8). Do NOT use city_norm.
- API, dropdown, and all filtering queries read from city_canonical.

## Server access
- Production VPS: ssh dude@185.229.226.190
- Repo root: ~/scrp
- Activate venv: source venv/bin/activate
- Load env: source .env
- Start scraper manually: python3 -m scripts.run_one <chain_id>
- Check API service: sudo systemctl status scrp-api
- Check cron: sudo journalctl -u scrp-cron -n 20 --no-pager

## Commit conventions
- Always use utf8NoBOM for commit messages:
  $msg = "type(scope): message"
  [System.IO.File]::WriteAllText("$pwd\.git\COMMIT_MSG_TMP", $msg, [System.Text.UTF8Encoding]::new($false))
  git commit -F .git\COMMIT_MSG_TMP
- Never amend + force-push to fix a BOM after the fact

## Deploy frontend
.\scripts\deploy_frontend.ps1

## Key file locations
- Scraper registry: scraper/registry.py
- City normalization: scraper/city_names.py (CITY_VARIANTS, STORE_CITY_OVERRIDES)
- Active stores: scraper/active_stores.yaml
- Cron entry: scraper/cron_main.py
- DB queries: db/query.py
- API routes: api/routers/

## Current stack (June 2026)
- 15 chains in registry
- ~700+ stores in active_stores.yaml
- Postgres on Kamatera, backed up to Backblaze B2 via rclone
- Frontend: React/Vite → nginx on Kamatera (185.229.226.190)
- SSL: Let's Encrypt via certbot (auto-renews)
- Cron: systemd scrp-cron, runs 03:00 IDT
