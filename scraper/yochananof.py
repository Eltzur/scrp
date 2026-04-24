"""Yochananof scraper — Cerberus portal."""
import logging
import sys

from scraper.cerberus import CerberusScraper

log = logging.getLogger(__name__)


class YochananofScraper(CerberusScraper):
    CHAIN_ID   = "7290803800003"
    USERNAME   = "yohananof"
    CHAIN_NAME = "יוחננוף"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    city   = next((a for a in sys.argv[1:] if not a.startswith("-")), "ירושלים")
    n      = int(next((sys.argv[i+1] for i, a in enumerate(sys.argv) if a == "-n"), 5))
    keep   = "--keep-raw" in sys.argv
    append = "--append" in sys.argv
    YochananofScraper().run(city=city, n_stores=n, keep_raw=keep, append=append)
