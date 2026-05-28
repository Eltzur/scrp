from scraper.binaprojects import BinaProjectsScraper


class ShukHayirScraper(BinaProjectsScraper):
    BASE_URL   = "https://shuk-hayir.binaprojects.com"
    CHAIN_NAME = "שוק העיר"
    CHAIN_ID   = "7290058148776"
