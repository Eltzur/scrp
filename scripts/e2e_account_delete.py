"""End-to-end check of DELETE /account on the real stack (SU11A-29). THROWAWAY ACCOUNTS ONLY.

Run by hand on the server, never from CI and never by an agent:
    cd ~/scrp && set -a && . ./.env && set +a
    venv/bin/python3 -m scripts.e2e_account_delete --email <throwaway email> --dry-run
    venv/bin/python3 -m scripts.e2e_account_delete --email <throwaway email>

It signs in as the throwaway account (password typed hidden via getpass), counts that
account's rows (SELECTs only, read-only transaction), and - only without --dry-run and
only after the email is typed again - calls DELETE /account. Then it proves the rows
are gone, the login is gone, and the old token cannot bring the account back.

Safety gates before anything is deleted: the endpoint must answer an unauthenticated
DELETE with 401/403 (deployed); deleted_accounts must exist (migration applied); the
user id must not be in DELETE_PROTECTED_USER_IDS; users.tier must be 'free' (an account
with no users row has never called the API and cannot be 'paid'); the signed-in email
must equal --email.

Never printed: the password, tokens, the anon key, DATABASE_URL. Errors show HTTP
status codes and Supabase's short error_code only.
Exit code: 0 = every check passed; 2 = deletion pending (202, the sweep must finish
it); 1 = a check failed or a gate stopped the run.
"""
from __future__ import annotations

import argparse
import getpass
import os
import sys

import httpx
from sqlalchemy import create_engine, text

REQUIRED_ENV = ("SUPABASE_URL", "SUPABASE_ANON_KEY", "DATABASE_URL")
OPTIONAL_ENV = ("DELETE_PROTECTED_USER_IDS",)
TIMEOUT_S = 20.0

# (label, SQL). :uid is the Supabase user id; flights / deleted_accounts columns are uuid.
COUNTS = [
    ("users", "SELECT count(*) FROM users WHERE id = :uid"),
    ("saved_baskets", "SELECT count(*) FROM saved_baskets WHERE user_id = :uid"),
    ("favorites", "SELECT count(*) FROM favorites WHERE user_id = :uid"),
    ("ratings", "SELECT count(*) FROM ratings WHERE user_id = :uid"),
    ("rating_reports (filed by user)", "SELECT count(*) FROM rating_reports WHERE reporter_user_id = :uid"),
    ("flights.alerts", "SELECT count(*) FROM flights.alerts WHERE user_id = CAST(:uid AS uuid)"),
    ("flights.saved_searches", "SELECT count(*) FROM flights.saved_searches WHERE user_id = CAST(:uid AS uuid)"),
    ("deleted_accounts", "SELECT count(*) FROM deleted_accounts WHERE user_id = CAST(:uid AS uuid)"),
]
MUST_BE_ZERO = [label for label, _ in COUNTS if label != "deleted_accounts"]


class Gate(Exception):
    """A safety gate stopped the run before anything was deleted."""


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    ap = argparse.ArgumentParser(
        description="End-to-end DELETE /account check on the real stack. Throwaway accounts only.")
    ap.add_argument("--email", required=True, help="the throwaway account's email")
    ap.add_argument("--api-base", default="https://api-super.xxl.co.il", help="API base URL")
    ap.add_argument("--dry-run", action="store_true",
                    help="sign in and count rows, never call DELETE /account")
    return ap.parse_args(argv)


def missing_env(environ=os.environ) -> list[str]:
    """Names of required variables that are unset or empty. Never values."""
    return [name for name in REQUIRED_ENV if not environ.get(name)]


def normalize_db_url(url: str) -> str:
    """Same rule as db/db.py (postgres:// -> postgresql://), plus dropping an async
    driver suffix (postgresql+asyncpg://) so the sync psycopg2 driver is used."""
    if url.startswith("postgres://"):
        url = "postgresql://" + url[len("postgres://"):]
    scheme, sep, rest = url.partition("://")
    if "+" in scheme:
        scheme = scheme.split("+", 1)[0]
    return f"{scheme}{sep}{rest}"


def protected_ids(environ=os.environ) -> set[str]:
    raw = environ.get("DELETE_PROTECTED_USER_IDS", "")
    return {p.strip().lower() for p in raw.split(",") if p.strip()}


class Report:
    def __init__(self):
        self.results: list[tuple[str, str]] = []

    def check(self, name: str, ok: bool, reason: str) -> bool:
        status = "PASS" if ok else "FAIL"
        self.results.append((name, status))
        print(f"[{status}] {name}: {reason}")
        return ok

    def skip(self, name: str, reason: str) -> None:
        self.results.append((name, "SKIP"))
        print(f"[SKIP] {name}: {reason}")

    @property
    def failed(self) -> int:
        return sum(1 for _, s in self.results if s == "FAIL")


def _err_code(resp: httpx.Response) -> str:
    """Short, non-secret description of an error response."""
    try:
        body = resp.json()
    except ValueError:
        return f"HTTP {resp.status_code}"
    code = None
    if isinstance(body, dict):
        code = body.get("code") or body.get("error_code") or body.get("error")
        if isinstance(code, int):
            code = body.get("error_code")
    return f"HTTP {resp.status_code}" + (f" {code}" if isinstance(code, str) else "")


def sign_in(http: httpx.Client, supabase_url: str, anon_key: str, email: str, password: str):
    """Returns (response, access_token, user_id, user_email); tokens stay in memory only."""
    resp = http.post(
        f"{supabase_url.rstrip('/')}/auth/v1/token",
        params={"grant_type": "password"},
        headers={"apikey": anon_key},
        json={"email": email, "password": password},
    )
    if resp.status_code != 200:
        return resp, None, None, None
    body = resp.json()
    user = body.get("user") or {}
    return resp, body.get("access_token"), user.get("id"), (user.get("email") or "")


def counts(engine, uid: str) -> dict[str, int]:
    out = {}
    with engine.connect() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        for label, sql in COUNTS:
            out[label] = int(conn.execute(text(sql), {"uid": uid}).scalar() or 0)
        conn.rollback()
    return out


def deleted_row(engine, uid: str):
    with engine.connect() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        row = conn.execute(text(
            "SELECT auth_deleted_at, attempts, last_error FROM deleted_accounts "
            "WHERE user_id = CAST(:uid AS uuid)"), {"uid": uid}).first()
        conn.rollback()
    return row


def tier_of(engine, uid: str):
    with engine.connect() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        row = conn.execute(text("SELECT tier FROM users WHERE id = :uid"), {"uid": uid}).first()
        conn.rollback()
    return None if row is None else row[0]


def has_deleted_accounts(engine) -> bool:
    with engine.connect() as conn:
        conn.execute(text("SET TRANSACTION READ ONLY"))
        found = conn.execute(text("SELECT to_regclass('public.deleted_accounts')")).scalar()
        conn.rollback()
    return found is not None


def print_counts(title: str, c: dict[str, int]) -> None:
    print(f"\n{title}")
    width = max(len(k) for k in c)
    for k, v in c.items():
        print(f"  {k.ljust(width)}  {v}")
    print()


def run(args: argparse.Namespace) -> int:
    missing = missing_env()
    if missing:
        print("Missing environment variable(s): " + ", ".join(missing)
              + ". Source the server .env with: set -a && . ./.env && set +a")
        return 1

    supabase_url = os.environ["SUPABASE_URL"]
    anon_key = os.environ["SUPABASE_ANON_KEY"]
    api = args.api_base.rstrip("/")
    engine = create_engine(normalize_db_url(os.environ["DATABASE_URL"]), pool_pre_ping=True)
    rep = Report()

    print(f"e2e DELETE /account - api {api} - {'DRY RUN' if args.dry_run else 'REAL RUN'}")
    print("THROWAWAY ACCOUNTS ONLY.\n")

    with httpx.Client(timeout=TIMEOUT_S) as http:
        try:
            # a. endpoint is deployed and refuses anonymous callers
            r = http.delete(f"{api}/account")
            if not rep.check("a. unauthenticated DELETE /account", r.status_code in (401, 403),
                             f"HTTP {r.status_code} (expected 401/403)"):
                raise Gate("DELETE /account is not answering as deployed")

            # b. sign in
            password = getpass.getpass(f"Password for {args.email} (hidden): ")
            r, token, uid, signed_email = sign_in(http, supabase_url, anon_key, args.email, password)
            if not rep.check("b. sign in", bool(token and uid),
                             "signed in" if token and uid else _err_code(r)):
                raise Gate("cannot sign in")

            # c. safety gates
            if not rep.check("c1. user id not protected", uid.lower() not in protected_ids(),
                             f"user_id={uid}"):
                raise Gate("this account is listed in DELETE_PROTECTED_USER_IDS")
            if not rep.check("c2. signed-in email equals --email",
                             signed_email.strip().lower() == args.email.strip().lower(),
                             "match" if signed_email.strip().lower() == args.email.strip().lower()
                             else "the signed-in account has a different email"):
                raise Gate("email mismatch")
            if not rep.check("c3. deleted_accounts table exists", has_deleted_accounts(engine),
                             "migration su11a28 applied"):
                raise Gate("apply db/migrations/su11a28_deleted_accounts.sql first")
            tier = tier_of(engine, uid)
            tier_ok = tier in (None, "free")
            if not rep.check("c4. tier is free", tier_ok,
                             "no users row yet (never called the API; defaults to free)" if tier is None
                             else f"tier={tier}"):
                raise Gate("only 'free' accounts may be deleted by this script")

            # d. counts before
            before = counts(engine, uid)
            print_counts(f"Rows for user_id={uid} before:", before)
            if before["deleted_accounts"]:
                print("Note: this id already has a deleted_accounts row (an earlier attempt).")
            if args.dry_run:
                print(f"DRY RUN complete: {len(rep.results)} checks, {rep.failed} failed. Nothing deleted.")
                return 0 if rep.failed == 0 else 1

            # e. typed confirmation
            typed = input(f"Type the email again to DELETE this account ({args.email}): ").strip()
            if typed.lower() != args.email.strip().lower():
                print("Confirmation did not match. Nothing deleted.")
                return 1

        except Gate as g:
            print(f"\nSTOPPED before any deletion: {g}.")
            return 1

        # f. delete
        r = http.delete(f"{api}/account", headers={"Authorization": f"Bearer {token}"})
        pending = r.status_code == 202
        if pending:
            rep.check("f. DELETE /account", True, f"{_err_code(r)} - deletion pending; the sweep "
                      "(scripts/sweep_account_deletes.py) must finish the Supabase delete")
        else:
            rep.check("f. DELETE /account", r.status_code == 204, f"{_err_code(r)} (expected 204)")
            if r.status_code not in (202, 204):
                print("DELETE did not succeed; recounting so the state is visible.")

        # g. recount
        after = counts(engine, uid)
        print_counts(f"Rows for user_id={uid} after:", after)
        for label in MUST_BE_ZERO:
            rep.check(f"g. {label} = 0", after[label] == 0, f"{after[label]}")
        row = deleted_row(engine, uid)
        if row is None:
            rep.check("g. deleted_accounts row", False, "no row")
        elif pending:
            rep.check("g. deleted_accounts row pending", row.auth_deleted_at is None,
                      f"auth_deleted_at={'set' if row.auth_deleted_at else 'NULL'}, attempts={row.attempts}, "
                      f"last_error={row.last_error}")
        else:
            rep.check("g. deleted_accounts row done", row.auth_deleted_at is not None,
                      f"auth_deleted_at={'set' if row.auth_deleted_at else 'NULL'}")

        # h. the login is gone
        if pending:
            rep.skip("h. sign in again fails", "auth user still exists while the deletion is pending")
        else:
            r2, token2, _, _ = sign_in(http, supabase_url, anon_key, args.email, password)
            rep.check("h. sign in again fails", token2 is None,
                      _err_code(r2) if token2 is None else "Supabase still accepts the login")
        password = None  # noqa: F841 - drop the reference as soon as it is no longer needed

        # i. old token on a normal endpoint
        r = http.get(f"{api}/favorites", headers={"Authorization": f"Bearer {token}"})
        code = _err_code(r)
        rep.check("i. old token on GET /favorites", r.status_code == 401,
                  code + (" (account_deleted)" if "account_deleted" in code
                          else " (token rejected before the deleted-accounts check)" if r.status_code == 401
                          else ""))
        users_now = counts(engine, uid)["users"]
        rep.check("i. users row still absent", users_now == 0, f"users={users_now}")

        # j. repeat DELETE with the old token
        r = http.delete(f"{api}/account", headers={"Authorization": f"Bearer {token}"})
        code = _err_code(r)
        if r.status_code == 204:
            rep.check("j. repeat DELETE /account", True, "204 - safe repeat (Supabase 404 counts as success)")
        elif r.status_code == 202:
            rep.check("j. repeat DELETE /account", True, "202 - still pending; the sweep will finish it")
        elif r.status_code == 401:
            why = ("the old token is over 300 s old (fresh sign-in required)" if "reauth_required" in code
                   else "the old token has expired")
            rep.check("j. repeat DELETE /account", True, f"{code} - {why}")
        else:
            rep.check("j. repeat DELETE /account", False, f"{code} (expected 204, 202 or 401)")
        final = counts(engine, uid)
        ok_after = all(final[k] == 0 for k in MUST_BE_ZERO) and final["deleted_accounts"] == 1
        rep.check("j. nothing broke", ok_after,
                  f"app rows {sum(final[k] for k in MUST_BE_ZERO)}, deleted_accounts {final['deleted_accounts']}")

    token = None  # noqa: F841
    total, failed = len(rep.results), rep.failed
    if failed:
        print(f"\nSUMMARY: FAIL - {failed} of {total} checks failed for user_id={uid}.")
        return 1
    if pending:
        print(f"\nSUMMARY: PENDING - app data deleted, Supabase delete pending for user_id={uid}; "
              "run scripts/sweep_account_deletes.py, then sign-in should fail.")
        return 2
    print(f"\nSUMMARY: PASS - all {total} checks passed; account user_id={uid} is deleted.")
    return 0


def main(argv: list[str] | None = None) -> int:
    return run(parse_args(argv))


if __name__ == "__main__":
    sys.exit(main())
