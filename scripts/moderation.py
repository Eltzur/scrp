"""Moderate ratings from the server (SU11A-44). Run by Dude, never by CC.

    cd ~/scrp && venv/bin/python3 -m scripts.moderation queue
    venv/bin/python3 -m scripts.moderation hide    <rating_id> [--yes]
    venv/bin/python3 -m scripts.moderation keep    <rating_id> [--yes]
    venv/bin/python3 -m scripts.moderation restore <rating_id> [--yes]
    venv/bin/python3 -m scripts.moderation ban     <rating_id> [--yes]
    venv/bin/python3 -m scripts.moderation unban   <rating_id> [--yes]

queue    ratings that need a moderator (api/moderation.py has the rule)
hide     status -> hidden          keep     status unchanged, leaves the queue
restore  status -> active          (all three stamp reviewed_at)
ban      ban the rating's author and hide all their active ratings
unban    clear the author's ban (hidden ratings stay hidden; restore one by one)

Mutating commands print what they would change and do nothing without --yes.
Output carries rating ids, item codes, statuses, report reasons and comment
excerpts only: never an email, a user id or a secret. Loads ~/scrp/.env itself.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

from sqlalchemy import text

ROOT = Path(__file__).resolve().parent.parent
EXCERPT = 80


def _excerpt(s: str | None) -> str:
    s = " ".join((s or "").split())
    return (s[:EXCERPT] + "…") if len(s) > EXCERPT else (s or "(no comment)")


def print_queue(conn, out=print) -> int:
    from api.moderation import queue

    items = queue(conn)
    conn.rollback()
    out(f"{len(items)} rating(s) need a moderator")
    for r in items:
        out(f"- rating {r['id']}  item {r['item_code']}  status {r['status']}  "
            f"rating {r['rating']}  reports {r['report_count']} "
            f"({', '.join(r['report_sources']) or 'none'})  latest {r['latest_report_at'] or '-'}")
        out(f"    comment: {_excerpt(r['comment'])}")
        for reason in r["report_reasons"][:5]:
            out(f"    reason:  {_excerpt(reason)}")
    return 0


def _current(conn, rating_id: int):
    row = conn.execute(text("SELECT item_code, status FROM ratings WHERE id = :id"),
                       {"id": rating_id}).mappings().first()
    conn.rollback()
    return row


def run(conn, command: str, rating_id: int | None, yes: bool, out=print) -> int:
    from api import moderation

    if command == "queue":
        return print_queue(conn, out)

    if command in moderation.ACTIONS:
        row = _current(conn, rating_id)
        if row is None:
            out(f"rating {rating_id} not found")
            return 1
        new = {"hide": "hidden", "keep": row["status"], "restore": "active"}[command]
        out(f"{command}: rating {rating_id} (item {row['item_code']}) status "
            f"{row['status']} -> {new}, reviewed_at -> now")
        if not yes:
            out("dry run: nothing changed (add --yes to apply)")
            return 0
        moderation.moderate(conn, rating_id, command)
        out("done")
        return 0

    # ban / unban
    preview = moderation.author_preview(conn, rating_id)
    if preview is None:
        out(f"rating {rating_id} not found")
        return 1
    if command == "ban":
        out(f"ban: the author of rating {rating_id} (item {preview['item_code']}); "
            f"already banned: {'yes' if preview['banned'] else 'no'}; "
            f"{preview['active_ratings']} active rating(s) would be hidden")
    else:
        out(f"unban: the author of rating {rating_id} (item {preview['item_code']}); "
            f"currently banned: {'yes' if preview['banned'] else 'no'}; ratings stay as they are")
    if not yes:
        out("dry run: nothing changed (add --yes to apply)")
        return 0
    result = moderation.ban_author(conn, rating_id, command == "ban")
    out(f"done (ratings hidden: {result['ratings_hidden']})")
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("command", choices=["queue", "hide", "keep", "restore", "ban", "unban"])
    ap.add_argument("rating_id", nargs="?", type=int)
    ap.add_argument("--yes", action="store_true", help="apply the change (default: dry run)")
    args = ap.parse_args(argv)
    if args.command != "queue" and args.rating_id is None:
        ap.error(f"{args.command} needs a rating_id")

    from dotenv import load_dotenv
    load_dotenv(ROOT / ".env", override=False)
    from db.db import connect

    with connect() as conn:
        return run(conn, args.command, args.rating_id, args.yes)


if __name__ == "__main__":
    sys.exit(main())
