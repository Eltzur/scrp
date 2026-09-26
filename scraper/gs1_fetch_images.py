"""Fetch GS1 product imagery, resize, and store (phase 2b).

The media endpoint returns a base64-encoded JPEG in JSON — NOT a URL:

    GET /external/product/{gtin}/files?media=all&default_image=1&hq=1
    -> {"file": "<base64>"}

Originals are enormous: measured average 2.83 MB, up to 4800x4800 px. Storing
them raw for the ~11.5k matched products would need ~32 GB on a 30 GB volume.
So every image is resized to max 800 px / JPEG quality 80 **in memory** and only
the resized copy is ever written — raw bytes never touch disk. Measured
reduction: 97.4%, averaging 75.8 KB out, ~0.83 GB for the full set.

SCOPE: the same population as gs1_fetch_detail.py — one active GS1 row per GTIN,
restricted to GTINs that appear in items. Imagery for products nobody sells is a
wasted 2.8 MB download.

RESUMABLE: an existing output file is skipped, so an interrupted run can simply
be relaunched. --refresh forces a re-fetch.

RATE LIMITS: the media endpoint blocks after roughly 1,800 requests in one
sitting (SU10S-3) and answers HTTP 400 until it clears. The run aborts after
10 consecutive 400s and exits non-zero rather than burning the rest of the
batch. Keep --limit well under that threshold when scheduling; the weekly
timer uses 1500.

STALE-CACHE NOTE: when GS1 answers 200 with no "file", the imagery was removed
upstream and any local copy is deleted (see _fetch_and_resize). Because the
default run SKIPS GTINs that already have a file, that check only happens under
--refresh — which is exactly the population that can hold a stale image. A plain
run will never delete anything.

NOT web-served: the default output directory is outside any nginx root. Wiring
it up for serving is a separate, deliberate step.

Dry run (fetches + resizes, writes nothing):
    python3 -m scraper.gs1_fetch_images --dry-run --limit 10

Full pull (detached, ~11.5k images):
    nohup python3 -m scraper.gs1_fetch_images > /tmp/gs1_images.log 2>&1 &
"""
import base64
import io
import logging
import os
import time
from pathlib import Path

import requests
from dotenv import load_dotenv
from PIL import Image
from sqlalchemy import text

from db.db import connect

log = logging.getLogger(__name__)

load_dotenv(Path(__file__).resolve().parent.parent / ".env", override=False)

_MEDIA_URL = ("https://retailer.gs1ildigital.org/external/product/"
              "{gtin}/files?media=all&default_image=1&hq=1")

_DEFAULT_OUT = str(Path.home() / "gs1_images")
_MAX_PX = 800
_QUALITY = 80
# Lower than gs1_fetch_detail's 3.0: these payloads average 2.83 MB, so the
# transfer itself dominates and a higher rate just queues bandwidth.
_DEFAULT_RPS = 2.0
_HTTP_TIMEOUT = 120
_ACTIVE_STATUS = "פעיל"

# Consecutive HTTP 400s from the media endpoint before we stop the run.
#
# SU10S-3 measured the failure mode: after roughly 1,800 requests in one
# sitting at 2 req/s the endpoint starts answering 400 with a Hebrew body
# ("נחסמת בעקבות…" — "you have been blocked due to…") and does not recover
# within the run. Every request after that point is wasted and may well be
# extending the block. Ten in a row is far past any plausible run of
# per-product 400s, so it identifies the block without firing on noise.
_BLOCK_STREAK_LIMIT = 10

_TARGET_SQL = """
    WITH ranked AS (
        SELECT p.gtin,
               ROW_NUMBER() OVER (
                   PARTITION BY p.gtin
                   ORDER BY p.modification_timestamp DESC NULLS LAST, p.id DESC
               ) AS rn
        FROM gs1.products p
        WHERE p.product_status = :active AND p.gtin IS NOT NULL
    )
    SELECT DISTINCT r.gtin
    FROM ranked r
    JOIN items i ON i.item_code = r.gtin
    WHERE r.rn = 1
    ORDER BY r.gtin
"""


def _fetch_and_resize(session: requests.Session, gtin: str, out_path: str,
                      dry_run: bool) -> tuple[int, int] | str | None:
    """Return (raw_bytes, written_bytes), "no_image", "blocked", or None.

    The three outcomes are NOT interchangeable. "no_image" means GS1 answered
    200 and told us this GTIN has no imagery — an authoritative statement that
    any local copy is now stale. None means we could not get an answer at all
    (HTTP error, timeout, decode failure), which says nothing about whether the
    image still exists upstream. Only the first may be allowed to delete a file;
    conflating them would make one bad afternoon of 5xx responses wipe the
    cache. "blocked" is an HTTP 400, the endpoint's rate-limit response — a
    failure like None, split out only so the caller can detect a streak of
    them and stop the run. Raw bytes stay in memory.
    """
    resp = session.get(_MEDIA_URL.format(gtin=gtin), timeout=_HTTP_TIMEOUT)
    if resp.status_code != 200:
        log.warning("%s: HTTP %s %s", gtin, resp.status_code, resp.text[:80])
        # 400 is how the endpoint reports a rate-limit block. Distinguished
        # from other failures ONLY so run() can count a streak of them and
        # stop; it is still a plain failure, and like every other error path
        # it must never reach the delete branch.
        return "blocked" if resp.status_code == 400 else None
    b64 = (resp.json() or {}).get("file")
    if not b64:
        log.info("%s: no image available", gtin)
        return "no_image"

    raw = base64.b64decode(b64)
    im = Image.open(io.BytesIO(raw))
    im.load()
    if im.mode not in ("RGB", "L"):
        im = im.convert("RGB")
    im.thumbnail((_MAX_PX, _MAX_PX), Image.LANCZOS)

    if dry_run:
        buf = io.BytesIO()
        im.save(buf, "JPEG", quality=_QUALITY, optimize=True)
        return len(raw), buf.tell()

    im.save(out_path, "JPEG", quality=_QUALITY, optimize=True)
    return len(raw), os.path.getsize(out_path)


def run(out_dir: str = _DEFAULT_OUT, dry_run: bool = False, limit: int | None = None,
        refresh: bool = False, rps: float = _DEFAULT_RPS) -> dict:
    session = requests.Session()
    from scraper.gs1_fetch import _credentials
    session.auth = _credentials()

    os.makedirs(out_dir, exist_ok=True)
    conn = connect()
    t0 = time.monotonic()
    fetched = failed = skipped = 0
    # Split out of "failed": an upstream deletion is a successful answer, not a
    # fetch error, and lumping the two together is what hid the stale-cache bug.
    deleted = no_image = 0
    block_streak = 0
    aborted_blocked = False
    raw_total = out_total = 0
    try:
        gtins = [r["gtin"] for r in
                 conn.execute(text(_TARGET_SQL), {"active": _ACTIVE_STATUS}).mappings().all()]
        if limit:
            gtins = gtins[:limit]
        log.info("targets: %s   out: %s   %.1f req/s%s",
                 f"{len(gtins):,}", out_dir, rps, "   [DRY RUN]" if dry_run else "")

        min_interval = 1.0 / rps if rps > 0 else 0.0
        next_at = time.monotonic()

        for n, gtin in enumerate(gtins, 1):
            path = os.path.join(out_dir, f"{gtin}.jpg")
            if not refresh and not dry_run and os.path.exists(path):
                skipped += 1
                continue

            now = time.monotonic()
            if now < next_at:
                time.sleep(next_at - now)
            next_at = time.monotonic() + min_interval

            existed_before = os.path.exists(path)

            try:
                res = _fetch_and_resize(session, gtin, path, dry_run)
            except Exception as exc:
                log.warning("%s: %s: %s", gtin, type(exc).__name__, str(exc)[:100])
                res = None

            if res == "blocked":
                # Rate-limited. Counts as a failure exactly like any other,
                # and touches nothing on disk.
                failed += 1
                block_streak += 1
                if block_streak >= _BLOCK_STREAK_LIMIT:
                    remaining = len(gtins) - n
                    log.warning(
                        "media endpoint blocking — aborting run, %s remain for next run",
                        f"{remaining:,}")
                    aborted_blocked = True
                    break
                continue
            # Any answer that is not a block clears the streak: the limit is
            # about a sustained block, not a 400 here and there.
            block_streak = 0

            if res is None:
                # Transient — leave whatever is on disk alone.
                failed += 1
            elif res == "no_image":
                # GS1 confirmed there is no imagery for this GTIN. If we are
                # holding a copy, it is stale and must go: api/routers/product.py
                # ::_image_path() is a bare is_file() check with no upstream
                # cross-reference, so an orphaned JPEG is served indefinitely —
                # and under a 7-day immutable Cache-Control header at that.
                if existed_before and not dry_run:
                    os.remove(path)
                    log.info("%s: image removed upstream — deleted stale local cache", gtin)
                    deleted += 1
                else:
                    no_image += 1
            else:
                fetched += 1
                raw_total += res[0]
                out_total += res[1]

            if n % 200 == 0 or n == len(gtins):
                el = max(time.monotonic() - t0, 0.001)
                log.info("  %s/%s  ok=%s failed=%s skipped=%s deleted=%s no_image=%s"
                         "  (%.1f/s, %.2f GB written)",
                         f"{n:,}", f"{len(gtins):,}", f"{fetched:,}", f"{failed:,}",
                         f"{skipped:,}", f"{deleted:,}", f"{no_image:,}",
                         n / el, out_total / 1024**3)

        el = time.monotonic() - t0
        avg = out_total / fetched if fetched else 0
        log.info("DONE — fetched=%s failed=%s skipped=%s deleted=%s no_image=%s in %.0fs%s",
                 f"{fetched:,}", f"{failed:,}", f"{skipped:,}",
                 f"{deleted:,}", f"{no_image:,}", el,
                 "  [ABORTED — endpoint blocking]" if aborted_blocked else "")
        log.info("  raw downloaded : %.2f GB (never written to disk)", raw_total / 1024**3)
        log.info("  written        : %.2f GB   avg %.1f KB/image", out_total / 1024**3, avg / 1024)
        return {"fetched": fetched, "failed": failed, "skipped": skipped,
                "deleted": deleted, "no_image": no_image,
                "aborted_blocked": aborted_blocked,
                "raw_bytes": raw_total, "out_bytes": out_total, "seconds": el}
    finally:
        conn.close()


def main():
    import argparse

    logging.basicConfig(level=logging.INFO,
                        format="%(asctime)s %(levelname)s %(name)s: %(message)s")
    ap = argparse.ArgumentParser(description="Fetch + resize GS1 product imagery")
    ap.add_argument("--out", default=_DEFAULT_OUT, help=f"output dir (default {_DEFAULT_OUT})")
    ap.add_argument("--dry-run", action="store_true", help="fetch and resize but write nothing")
    ap.add_argument("--limit", type=int, help="only process the first N gtins")
    ap.add_argument("--refresh", action="store_true", help="re-fetch images that already exist")
    ap.add_argument("--rps", type=float, default=_DEFAULT_RPS,
                    help=f"requests per second (default {_DEFAULT_RPS})")
    args = ap.parse_args()
    stats = run(out_dir=args.out, dry_run=args.dry_run, limit=args.limit,
                refresh=args.refresh, rps=args.rps)
    # Non-zero so a blocked run is obvious in `systemctl status` and the
    # journal rather than looking like a clean finish with few images.
    if stats.get("aborted_blocked"):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
