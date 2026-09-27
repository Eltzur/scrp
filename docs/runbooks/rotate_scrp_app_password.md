# Runbook — rotate the `scrp_app` Postgres password

**Status:** not yet done. First flagged in 9d-2, when the password was printed
into a terminal and a chat transcript. It has been unchanged since.

**Who runs this:** Dude, interactively over SSH. Every step needs either `sudo`
or the password itself, so it cannot be automated from a session — and should
not be, since the value must never reach a command line or a log.

**When:** right after the 10:00 IDT cron finishes — it ends between 11:21 and
11:48 on observed days, so **roughly 12:00 is the safe window**. Rotating
before or during a run kills the scrape mid-flight: the cron holds connections
for its whole duration and re-authenticates per connection.

---

## 0. Know every consumer before touching anything

Enumerated on the server, SU10S-8. **The flights backend shares this
credential** — that is the one people forget, and forgetting it takes the
flights API down at the next restart rather than immediately.

| Consumer | Where the credential lives | Restart needed |
|---|---|---|
| `scrp-api` | `~/scrp/.env` → `DATABASE_URL` | yes |
| `scrp-cron` | `~/scrp/.env` (same file) | no — next run picks it up |
| `scrp-gs1-fetch` | `~/scrp/.env` (same file) | no — weekly timer |
| **`flights-api`** | **`~/xxl-flights/backend/.env` → `DATABASE_URL`** | **yes** |

Both `DATABASE_URL`s authenticate as `scrp_app`. Verify that nothing new has
appeared since:

```bash
grep -rl '^DATABASE_URL=' ~/scrp/.env ~/xxl-flights/backend/.env
grep -l 'EnvironmentFile' /etc/systemd/system/*.service \
  | xargs grep -h '^EnvironmentFile=' | sort -u
```

**Not affected, and worth knowing so you don't chase it:** `scrp-backup.sh`
runs `sudo -u postgres pg_dump`, i.e. peer authentication as the `postgres`
superuser. It never sees the `scrp_app` password, so backups keep working
throughout. Neither does anything rclone-related — B2 credentials are separate.

---

## 1. Generate the new password

Alphanumeric on purpose. The value goes into a `DATABASE_URL` **and** into a
systemd `EnvironmentFile`, and both have opinions about punctuation: `@`, `:`
and `/` break URL parsing, `#` starts a comment in an env file, `$` invites
expansion. Avoiding the whole class is cheaper than escaping it correctly in
two formats.

```bash
openssl rand -base64 48 | tr -dc 'A-Za-z0-9' | head -c 32; echo
```

Keep it in your password manager **before** going further. After step 2 the old
one stops working, and an un-saved new one means a locked-out database.

---

## 2. Change it in Postgres

```bash
sudo -u postgres psql -c "ALTER ROLE scrp_app WITH PASSWORD 'NEW_PASSWORD_HERE';"
```

Existing connections stay up — Postgres only checks the password on connect.
So nothing breaks at this instant; things break at the next reconnect, which
is why steps 3 and 4 follow immediately.

> `psql` history: `ALTER ROLE` statements are not written to `~/.psql_history`
> when passed with `-c`, but the shell's own history does record the command.
> Clear it afterwards: `history -d $((HISTCMD-1))`, or prefix the command with
> a space if `HISTCONTROL=ignorespace` is set.

---

## 3. Update both `.env` files — with an editor, never `echo` or `sed`

```bash
nano ~/scrp/.env                     # DATABASE_URL — replace the password segment
nano ~/xxl-flights/backend/.env      # DATABASE_URL — the same new password
```

**Use the editor.** `sed -i` and `echo >>` put the password in the shell
history and in the process list where any other user on the box can read it
with `ps`. That is the exact failure this rotation exists to correct.

The format is `postgresql://scrp_app:PASSWORD@localhost:5432/xxl_super` —
change only the segment between `scrp_app:` and `@localhost`.

---

## 4. Restart the two APIs

```bash
sudo /usr/local/bin/xxl-restart.sh scrp-api
sudo /usr/local/bin/xxl-restart.sh flights-api
```

Both read their environment from systemd's `EnvironmentFile`, which is re-read
only at unit start — editing `.env` alone changes nothing.

`scrp-cron` and `scrp-gs1-fetch` need no action: they are `oneshot` units that
read the same file when they next fire.

---

## 5. Verify — all four, in this order

```bash
# 1. scrp API actually queries the DB (not just answers)
curl -s -o /dev/null -w '%{http_code}\n' \
  http://127.0.0.1:8000/product/7290000363417/details      # expect 200

# 2. flights API
curl -s -o /dev/null -w '%{http_code}\n' http://127.0.0.1:8001/health   # expect 200

# 3. a real scraper connection, smallest chain, no writes beyond its own run
cd ~/scrp && source venv/bin/activate && set -a && source .env && set +a
python3 -c "from db.db import connect; from sqlalchemy import text; \
c=connect(); print('db ok:', c.execute(text('select current_user')).scalar()); c.close()"

# 4. backup path still fine (it uses peer auth, but confirm nothing else broke)
sudo /usr/local/bin/scrp-backup.sh && tail -5 /var/log/scrp-backup.log
```

Then watch the **next** 10:00 cron run to completion — that is the only thing
that exercises every connection path under load:

```bash
journalctl -u scrp-cron -n 40 --no-pager | tail -20   # expect "Cron finished ... Errors: none"
```

---

## 6. Rollback

The old password still works everywhere until step 2 runs, and nothing is
destroyed by it — so rollback is simply setting it back:

```bash
sudo -u postgres psql -c "ALTER ROLE scrp_app WITH PASSWORD 'OLD_PASSWORD_HERE';"
```

…then revert both `.env` files and restart both APIs again. This is why the old
password must stay in your password manager until step 5 has fully passed,
including the next cron run — **not** deleted as soon as the new one is set.

---

## Afterwards

- Delete `~/scrp/.env.bak-su10s7` once mail and DB are both confirmed healthy;
  it holds the pre-SMTP copy of `.env` and therefore the **old** password.
- The credential was exposed in a 9d-2 chat transcript. Rotating closes that,
  but the transcript itself is still out there — treat the old value as public
  from here on.
