"""Osher Ad scraper — thin subclass of CerberusScraper."""
import logging
import sys

from scraper.cerberus import CerberusScraper

log = logging.getLogger(__name__)


class OsherAdScraper(CerberusScraper):
    CHAIN_ID   = "7290103152017"
    USERNAME   = "osherad"
    CHAIN_NAME = "אושר עד"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    city = sys.argv[1] if len(sys.argv) > 1 else "ירושלים"
    n    = int(sys.argv[2]) if len(sys.argv) > 2 else 5
    keep = "--keep-raw" in sys.argv
    OsherAdScraper().run(city=city, n_stores=n, keep_raw=keep)
