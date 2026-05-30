"""Paz (Alonit) scraper — thin subclass of CerberusScraper."""
from scraper.cerberus import CerberusScraper


class PazScraper(CerberusScraper):
    CHAIN_ID   = "7290644700005"
    USERNAME   = "paz"
    CHAIN_NAME = "פז"
