"""Fresh Market scraper — thin subclass of CerberusScraper."""
from scraper.cerberus import CerberusScraper


class FreshMarketScraper(CerberusScraper):
    CHAIN_ID   = "7290876100000"
    USERNAME   = "freshmarket"
    CHAIN_NAME = "פרש מרקט"
