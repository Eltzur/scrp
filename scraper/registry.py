"""Chain registry: chain_id -> scraper class."""
from scraper.shufersal import ShufersalScraper
from scraper.ramilevi import RamiLeviScraper
from scraper.osherad import OsherAdScraper
from scraper.victory import VictoryScraper
from scraper.yochananof import YochananofScraper
from scraper.keshet import KeshetScraper
from scraper.carrefour import CarrefourScraper
from scraper.tivtaam import TivTaamScraper
from scraper.kingstore import KingStoreScraper
from scraper.shefabirkat import ShefaBirkatHashemScraper
from scraper.shukhayir   import ShukHayirScraper
from scraper.freshmarket import FreshMarketScraper
from scraper.yuda        import YudaScraper
from scraper.hazihinam   import HaziHinamScraper

SCRAPERS: dict[str, type] = {
    "7290027600007": ShufersalScraper,
    "7290058140886": RamiLeviScraper,
    "7290103152017": OsherAdScraper,
    "7290696200003": VictoryScraper,
    "7290803800003": YochananofScraper,
    "7290785400000": KeshetScraper,
    "7290055700007": CarrefourScraper,
    "7290873255550": TivTaamScraper,
    "7290058108879": KingStoreScraper,
    "7290058134977": ShefaBirkatHashemScraper,
    "7290058148776": ShukHayirScraper,
    "7290876100000": FreshMarketScraper,
    "7290058177776": YudaScraper,
    "7290700100008": HaziHinamScraper,
}


DELTA_CHAINS: set[str] = {
    "7290027600007",  # Shufersal       — own lazy-fetch implementation
    "7290058140886",  # Rami Levy       — Cerberus
    "7290103152017",  # Osher Ad        — Cerberus
    "7290803800003",  # Yochananof      — Cerberus
    "7290785400000",  # Keshet          — Cerberus
    "7290876100000",  # Fresh Market    — Cerberus
    "7290058177776",  # Super Yuda      — Cerberus
    "7290700100008",  # Hazi Hinam      — custom portal, own build_price_index
    # Excluded — build_price_index not implemented for their portal type:
    # Tiv Taam     (7290873255550) — Cerberus but no daily Price delta files
    # Carrefour    (7290055700007) — PublishPrice portal
    # Victory      (7290696200003) — custom REST API
    # King Store   (7290058108879) — Bina Projects
    # Shefa        (7290058134977) — Bina Projects
    # Shuk Hayir   (7290058148776) — Bina Projects
}


def get_scraper(chain_id: str):
    """Return an instantiated scraper for the given chain_id, or None."""
    cls = SCRAPERS.get(chain_id)
    return cls() if cls else None


def uses_delta(chain_id: str) -> bool:
    """Return True if this chain should use Price (delta) files instead of PriceFull."""
    return chain_id in DELTA_CHAINS
