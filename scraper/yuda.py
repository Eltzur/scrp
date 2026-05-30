"""Yuda scraper — thin subclass of CerberusScraper."""
from scraper.cerberus import CerberusScraper


class YudaScraper(CerberusScraper):
    CHAIN_ID   = "7290058177776"
    USERNAME   = "yuda"
    CHAIN_NAME = "סופר יודה"
