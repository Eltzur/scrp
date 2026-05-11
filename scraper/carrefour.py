"""Carrefour Israel scraper — PublishPrice portal.

Covers Carrefour Hyper, Carrefour Market, Carrefour City, Mega, and
Yenot Bitan stores — all operated by Global Retail C.I. Ltd under
chain_id 7290055700007. We display the parent brand as "קרפור".

Portal: https://prices.carrefour.co.il/ (public HTTP, no auth)
"""
import logging
import sys

from scraper.publishprice import PublishPriceScraper

log = logging.getLogger(__name__)


class CarrefourScraper(PublishPriceScraper):
    CHAIN_ID   = "7290055700007"
    SITE_INFIX = "carrefour"
    CHAIN_NAME = "קרפור"


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO, format="%(message)s")
    city   = next((a for a in sys.argv[1:] if not a.startswith("-")), "תל אביב")
    n      = int(next((sys.argv[i + 1] for i, a in enumerate(sys.argv) if a == "-n"), 5))
    keep   = "--keep-raw" in sys.argv
    append = "--append" in sys.argv
    CarrefourScraper().run(city=city, n_stores=n, keep_raw=keep, append=append)
