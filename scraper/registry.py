"""Chain registry: chain_id → scraper class."""
from scraper.shufersal import ShufersalScraper
from scraper.ramilevi import RamiLeviScraper
from scraper.osherad import OsherAdScraper

SCRAPERS: dict[str, type] = {
    "7290027600007": ShufersalScraper,
    "7290058140886": RamiLeviScraper,
    "7290103152017": OsherAdScraper,
}


def get_scraper(chain_id: str):
    """Return an instantiated scraper for the given chain_id, or None."""
    cls = SCRAPERS.get(chain_id)
    return cls() if cls else None
