"""Chain registry: chain_id -> scraper class."""
from scraper.shufersal import ShufersalScraper
from scraper.ramilevi import RamiLeviScraper
from scraper.osherad import OsherAdScraper
from scraper.victory import VictoryScraper
from scraper.yochananof import YochananofScraper
from scraper.keshet import KeshetScraper
from scraper.carrefour import CarrefourScraper

SCRAPERS: dict[str, type] = {
    "7290027600007": ShufersalScraper,
    "7290058140886": RamiLeviScraper,
    "7290103152017": OsherAdScraper,
    "7290696200003": VictoryScraper,
    "7290803800003": YochananofScraper,
    "7290785400000": KeshetScraper,
    "7290055700007": CarrefourScraper,
}


def get_scraper(chain_id: str):
    """Return an instantiated scraper for the given chain_id, or None."""
    cls = SCRAPERS.get(chain_id)
    return cls() if cls else None
