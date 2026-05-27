"""Tiv Taam price scraper.

Cerberus portal (url.retail.publishedprices.co.il), username-only auth.
Added 9d-3 / P5. 46 retail stores; 7 ליקוט warehouse nodes excluded.
"""
from scraper.cerberus import CerberusScraper


class TivTaamScraper(CerberusScraper):
    USERNAME   = "TivTaam"
    CHAIN_NAME = "טיב טעם"
    CHAIN_ID   = "7290873255550"
