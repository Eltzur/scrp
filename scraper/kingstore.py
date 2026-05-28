"""King Store price scraper.

bina-projects portal (kingstore.binaprojects.com), no auth required.
Added 9d-3 / P6.
"""
from scraper.binaprojects import BinaProjectsScraper


class KingStoreScraper(BinaProjectsScraper):
    BASE_URL   = "https://kingstore.binaprojects.com"
    CHAIN_NAME = "קינג סטור"
    CHAIN_ID   = "7290058108879"
