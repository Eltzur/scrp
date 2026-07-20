# XXL Scraper — Claude Code Operating Guide

## Project context
Israeli supermarket price comparison app. Backend: FastAPI + SQLAlchemy + Postgres on Kamatera VPS (185.229.226.190). Frontend: React/Vite served via nginx on same VM. Scrapers: Python, pulling from Israel's government price transparency XML feeds. GitHub: github.com/Eltzur/scrp.

## Operating rules (apply every session)
1. **Short responses** — status/diagnosis, options with recommendation, then commands. No mid-stream pivots.
2. **Fool-proof** — delegate to CC as much as possible. Prompts in copy-paste blocks. Minimize manual effort.
3. **Read context first** — always read handoff.md and recent chats before starting work.
4. **Read-and-report-STOP** — on any code change touching scrapers or city resolution, show findings and stop before writing fixes.
5. **One CC prompt per task** — batch all related changes into one prompt. No incremental back-and-forth on simple tasks.
6. **Always push after commit** — CC must run `git push origin main` after every commit. Never leave commits only in local repo.

## Rules of engagement (chat architect -> operator -> CC)
The chat assistant is lead architect and plans; the operator executes verbatim; CC edits/commits. These govern how every instruction is delivered:
1. **Monoblock prompts.** One unified, copy-paste code block per CC task — never split a task across multiple snippets. The architect designs; the operator is the executioner.
2. **Environment tag on every block.** Prefix each code block with its environment:
   - `[CC]` — Claude Code, always running inside VS Code's integrated interface, working directory `C:\scrp`. There is no standalone/CLI-only CC in this workflow — every `[CC]` block is pasted into the VS Code Claude Code panel.
   - `[PowerShell - VS Code]` — a plain PowerShell terminal pane inside VS Code (not CC), same `C:\scrp` working directory, for manual commands the operator runs directly.
   - `[Bash - server]` — an SSH session directly on the Kamatera VPS (`dude@185.229.226.190`).
   - `[Bash - VS Code]` — a Git Bash/WSL terminal pane inside VS Code on the Windows machine, for commands that need bash syntax locally.
   - `[Notepad]` — a manual text edit the operator performs by hand, outside any code editor or CC.
3. **Strict first-come-first-served ordering.** The operator runs the first command in reading order, then keeps reading. Never issue a command and then retract or reorder it ("Wait - but first..."). Deliver every step in correct execution order the first time, even if composing it takes longer. Read-only/inspection commands always precede action commands. **All context, caveats, and flags belong BEFORE the code block, in the same message — never after.** Do not append "before you send this," "a few things worth flagging," or similar postambles once a task block has been delivered. If something needs flagging, flag it first, then give the block.

## Session naming convention
Every working session gets an ID, scoped by vertical. Use it in commit messages, handoff entries, and chat titles.

| Vertical | Format | Example | Handoff file |
|---|---|---|---|
| Supermarket | `SUXX-a/b/c` | `SU01-a` | `docs/super/handoff_super.md` |
| Flights | `FLXX-a/b/c` | `FL10A-6a` | `docs/flights/handoff_flights.md` |
| Consumer goods | `GEXX-a/b/c` | `GE01-a` | (TBD) |
| Portal / cross-cutting | `XXL-x.y.z` (semver) | `XXL-1.0.1` | `docs/handoff_portal.md` |

- `XX` = a two-digit session number; the trailing lowercase letter = sub-session (a/b/c...).
- **Flights continues the legacy `10A` lineage** — sessions before this convention were named `10A-*` (e.g. `10A-5b`, `10A-Q`). They are the SAME series; the `FL` prefix was added later. Do not renumber history. Next flights session: `FL10A-6a`.
- The portal uses semver rather than the `XX-a` form because it is the high-level surface spanning all verticals, not a single vertical's workstream.
- One chat = one session. Start a fresh chat at each session boundary and paste the relevant handoff as the first message.

## Permissions prompts
When a permission prompt appears for any of the commands below, always select "Yes, and don't ask again" (the option that permanently trusts the command):
- Any ssh command to dude@185.229.226.190
- Any scp command to dude@185.229.226.190
- Any git command (add, commit, push, pull, fetch)
- Any pip install command
- Any npm or npx command
- Any uvicorn command
- Any curl command

For all other commands, select "Yes" (one-time approval) unless the command looks destructive or unexpected.

## SEVERE warnings
- **RTL/Hebrew is NEVER a bug.** Hebrew in terminal/paste output often appears reversed — this is a display artifact, not a data bug. Never flag, never byte-check.
- **Railway is DEAD.** Project runs on Kamatera. Never reference Railway.
- **Never merge מודיעין עילית with מודיעין-מכבים-רעות** — separate municipalities.
- **Never merge BE-branded Shufersal stores into the main chain** — pharmacy/beauty only.
- **Promo data is CORRUPT** — Victory has 60K+ promo rows, data is unreliable. Do not build on promos table until a full audit and re-seed is done in a dedicated session.

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
- Get flights test-user token: `ssh dude@185.229.226.190 "~/xxl-flights/scripts/kamatera/get_test_token.sh"` — prints only the access_token to stdout; raw Supabase response to stderr + exit 1 on failure. See docs/flights/handoff_flights.md § Test user.
- Set flights test-user tier: `ssh dude@185.229.226.190 "~/xxl-flights/scripts/kamatera/set_test_tier.sh <free|paid>"` — interactive sudo password (not in the passwordless xxl-ops whitelist)

## Commit conventions
- Always use utf8NoBOM for commit messages:
  $msg = "type(scope): message"
  [System.IO.File]::WriteAllText("$pwd\.git\COMMIT_MSG_TMP", $msg, [System.Text.UTF8Encoding]::new($false))
  git commit -F .git\COMMIT_MSG_TMP
- Never amend + force-push to fix a BOM after the fact

## Hosting topology
- **Kamatera (185.229.226.190) is PRIMARY for ALL xxl.co.il surfaces**, all served by nginx on Kamatera:
  - Portal: xxl.co.il + www.xxl.co.il
  - Supermarket app: super.xxl.co.il
  - Flights: fly.xxl.co.il
  - API: api-super.xxl.co.il
- **Hostinger (82.198.227.247) is COLD FALLBACK / DR ONLY** — it holds an older static copy and receives no live traffic. Revert path: repoint the xxl.co.il + www A records at box.co.il back to 82.198.227.247.
- **Portal and supermarket app SHARE ONE React build (web/dist).** isPortalHostname() in web/src/utils/hostname.ts switches PortalPage vs AppShell at runtime by hostname. The xxl.co.il nginx block shares root /var/www/super.xxl.co.il, so deploying web/ updates BOTH super.xxl.co.il and xxl.co.il in a single deploy.

## Deploy frontend
.\scripts\deploy_frontend.ps1
- Builds web/ and scp's the output to /var/www/super.xxl.co.il on Kamatera. Because the xxl.co.il nginx block shares that same root, this updates BOTH super.xxl.co.il AND the portal (xxl.co.il / www.xxl.co.il) at once.
- The portal is NOT deployed via a Hostinger hPanel zip upload — that path is dead.

## Deploy flights backend + frontend
The flights vertical (xxl-flights repo) restarts and web-root deploys are passwordless via root-owned whitelist scripts (`/etc/sudoers.d/xxl-ops`, set up in FL10A-6a). No `-t` / no sudo prompt:
- Backend (after `git pull` + `pip install` in ~/xxl-flights): restart the service and print its logs —
  `ssh dude@185.229.226.190 "sudo /usr/local/bin/xxl-restart.sh flights-api"`
- Frontend: build from `C:\scrp\xxl-flights\frontend` (`npm run build`), scp `dist/*` to `~/fly_deploy`, then wipe+redeploy the www-data-owned web root —
  `ssh dude@185.229.226.190 "sudo /usr/local/bin/xxl-deploy-webroot.sh flights"`
- `xxl-restart.sh` also accepts `scrp-api`. The scripts case-match a fixed whitelist (no wildcards); extend by adding one case branch + one sudoers line, reviewed each time. Source lives in xxl-flights `scripts/kamatera/`.

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
- Frontend: React/Vite → nginx on Kamatera (185.229.226.190), serving portal (xxl.co.il), super (super.xxl.co.il), and flights (fly.xxl.co.il). See Hosting topology above.
- SSL: Let's Encrypt via certbot (auto-renews)
- Cron: systemd scrp-cron, runs 03:00 IDT
