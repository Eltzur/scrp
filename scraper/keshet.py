"""Keshet (קשת תמים) scraper — Cerberus portal."""
import logging
import sys

from scraper.cerberus import CerberusScraper

log = logging.getLogger(__name__)


class KeshetScraper(CerberusScraper):
    CHAIN_ID   = "7290785400000"
    USERNAME   = "Keshet"
    CHAIN_NAME = "קשת"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    city   = next((a for a in sys.argv[1:] if not a.startswith("-")), "ירושלים")
    n      = int(next((sys.argv[i+1] for i, a in enumerate(sys.argv) if a == "-n"), 5))
    keep   = "--keep-raw" in sys.argv
    append = "--append" in sys.argv
    KeshetScraper().run(city=city, n_stores=n, keep_raw=keep, append=append)
