#!/usr/bin/env python3
"""
One-time migration: normalize stores.store_id and sub_chain_id to
canonical zero-padded 3-digit format.

Background: publishprice.py historically stored Carrefour store_ids
unpadded ('6', '19'...) while cerberus.py zero-padded ('006'). Rami Levy
had sub_chain_id='1' vs '001' elsewhere. This inconsistency caused
silent-skip bugs in the 9j apply scripts. After this migration + the
publishprice.py/db.py code changes, all rows use one format.

SAFETY: a row's padded form may collide with an existing padded row
(e.g. both '6' and '006' present). The script detects collisions and
reports them WITHOUT merging — those need manual review. Everything
non-colliding is migrated.

Run:  python migrate_store_id_padding.py            # dry-run
      python migrate_store_id_padding.py --commit   # apply
"""
import os
import sys
from dotenv import load_dotenv
from sqlalchemy import create_engine, text


def pad(s: str) -> str:
    s = str(s).strip()
    return s.zfill(3) if s.isdigit() else s


def main():
    commit = "--commit" in sys.argv
    mode = "COMMIT" if commit else "DRY-RUN"
    print(f"\n{'='*60}\nSTORE_ID PADDING MIGRATION — {mode}\n{'='*60}\n")

    load_dotenv("/home/dude/scrp/.env")
    engine = create_engine(os.environ["DATABASE_URL"])

    with engine.begin() as conn:
        rows = conn.execute(text(
            "SELECT id, chain_id, sub_chain_id, store_id FROM stores "
            "ORDER BY chain_id, store_id"
        )).fetchall()

        # Build set of existing (chain_id, sub, store_id) for collision check
        existing = {(r[1], r[2], r[3]) for r in rows}

        to_migrate = []   # (id, chain_id, old_sub, new_sub, old_sid, new_sid)
        collisions = []

        for pk, chain_id, sub, sid in rows:
            new_sub = pad(sub)
            new_sid = pad(sid)
            if new_sub == sub and new_sid == sid:
                continue  # already canonical
            # Would the padded form collide with a different existing row?
            target = (chain_id, new_sub, new_sid)
            if target in existing and target != (chain_id, sub, sid):
                collisions.append((pk, chain_id, sub, sid, new_sub, new_sid))
            else:
                to_migrate.append((pk, chain_id, sub, new_sub, sid, new_sid))

        print(f"Rows scanned:    {len(rows)}")
        print(f"To migrate:      {len(to_migrate)}")
        print(f"Collisions:      {len(collisions)}  (need manual review — NOT migrated)\n")

        if collisions:
            print("COLLISIONS (padded form already taken by another row):")
            for pk, cid, sub, sid, nsub, nsid in collisions:
                print(f"  id={pk} chain={cid} {sub}/{sid} → {nsub}/{nsid} [BLOCKED]")
            print()

        if to_migrate:
            print("Migrations:")
            for pk, cid, sub, nsub, sid, nsid in to_migrate[:30]:
                print(f"  id={pk} chain={cid}  {sub}/{sid} → {nsub}/{nsid}")
            if len(to_migrate) > 30:
                print(f"  ...and {len(to_migrate)-30} more.")
            print()

        if not commit:
            print(f"{'='*60}\nDRY-RUN complete. Re-run with --commit to apply.\n{'='*60}")
            return

        for pk, cid, sub, nsub, sid, nsid in to_migrate:
            conn.execute(text(
                "UPDATE stores SET sub_chain_id=:nsub, store_id=:nsid WHERE id=:pk"
            ), {"nsub": nsub, "nsid": nsid, "pk": pk})

        print(f"✓ {len(to_migrate)} rows migrated.")
        if collisions:
            print(f"⚠ {len(collisions)} collisions skipped — review manually.")

    print(f"\n{'='*60}\nDone.\n{'='*60}")


if __name__ == "__main__":
    main()
