"""Dor Alon (AM:PM) scraper — thin subclass of CerberusScraper."""
from scraper.cerberus import CerberusScraper


class DorAlonScraper(CerberusScraper):
    CHAIN_ID   = "7290492000005"
    USERNAME   = "doralon"
    CHAIN_NAME = "דור אלון"
