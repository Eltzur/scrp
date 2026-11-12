# nginx files (SU11A-49)

Repo copies of the nginx configuration added for the SU11A-48 review findings F-02 (rate limits) and F-03 (security headers, CSP Report-Only, `server_tokens off`). They are NOT applied by any script: Dude installs them by following `docs/security/su11a49_runbook.md`, which lists every file, its destination (`/etc/nginx/conf.d/` or `/etc/nginx/snippets/`), the include lines, `nginx -t`, the checks and the rollback.

`api-noindex.conf` is a record of `/etc/nginx/snippets/api-noindex.conf`, applied by Dude on 22 Oct 2026 (backup `sites-available/api-super.xxl.co.il.bak-2026-10-22`). The live file wins if they ever differ.

`xxl-log-format.conf` (SU11A-69) adds the site name (`$host`) to the shared `access.log` for the admin statistics; installed by `docs/admin/su11a69_runbook.md` step 5, together with commenting out the plain `access_log` line in `/etc/nginx/nginx.conf`.

`xxl-spa-super.conf` (SU11A-81) is the SPA fallback of the super.xxl.co.il 443 `location /` (`try_files $uri /index.super.html;`, the per-host HTML for link previews); installed by the SU11A-81 entry in `docs/super/handoff_super.md` (web deploy first, then this).

When a live file is changed by hand, copy the change back here in the same session.
