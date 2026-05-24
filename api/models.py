"""Pydantic v2 response models for the Israeli Price Comparison API."""
from __future__ import annotations
from pydantic import BaseModel, ConfigDict, Field


class ChainSummary(BaseModel):
    """One loaded chain with aggregate stats."""
    model_config = ConfigDict(from_attributes=True)

    chain_id: str             = Field(description="Chain barcode prefix / government ID")
    name: str                 = Field(description="Hebrew chain name")
    total_barcodes: int       = Field(description="Distinct barcodes with prices loaded")
    total_stores_loaded: int  = Field(description="Stores we have price data for")


class Store(BaseModel):
    """A single supermarket branch."""
    model_config = ConfigDict(from_attributes=True)

    store_id: str
    chain_id: str
    chain_name: str | None    = Field(None, description="Hebrew chain name")
    store_name: str | None    = Field(None, description="Branch name / location label")
    city: str | None
    address: str | None


class PriceQuote(BaseModel):
    """One chain's best (cheapest store) price for a barcode."""
    chain_id: str
    chain_name: str | None
    store_id: str
    store_name: str | None
    city: str | None
    price: float              = Field(description="Item price in NIS")
    unit_price: float | None  = Field(None, description="Price per unit-of-measure")
    unit_of_measure: str | None
    updated_at: str | None    = Field(None, description="Date price was last updated in source XML")
    delta_from_cheapest: float = Field(0.0, description="How much more expensive than the cheapest chain (0 = cheapest)")


class Product(BaseModel):
    """Core product metadata, chain-agnostic."""
    item_code: str            = Field(description="Barcode / EAN")
    canonical_name: str | None = Field(None, description="Name from first chain to insert this barcode")
    manufacturer: str | None
    unit_of_measure: str | None
    is_weighted: bool         = Field(description="True for deli/cheese items priced per kg")
    names_per_chain: dict[str, str] = Field(
        default_factory=dict,
        description="chain_id → product name as that chain calls it",
    )


class ProductWithPrices(BaseModel):
    """A product together with all available price quotes."""
    product: Product
    quotes: list[PriceQuote]  = Field(description="One entry per chain, sorted cheapest first")
    cheapest_price: float | None
    most_expensive_price: float | None
    chains_count: int         = Field(description="Number of distinct chains carrying this barcode")


class CityInfo(BaseModel):
    """A city with price coverage statistics."""
    city: str
    chain_count: int           = Field(description="Number of distinct chains with prices in this city")
    store_count: int           = Field(description="Number of stores with prices in this city")
    price_count: int           = Field(description="Total price rows in this city")
    chain_ids: list[str]       = Field(default_factory=list, description="chain_ids present in this city")


class SearchResult(BaseModel):
    """Response for GET /search and GET /compare."""
    query: str
    total_matches: int        = Field(description="Distinct barcodes matching the query")
    comparable_count: int     = Field(description="Barcodes available in 2+ chains")
    has_more: bool            = Field(False, description="True when more results exist beyond current page")
    items: list[ProductWithPrices] = Field(
        description="Multi-chain products first (sorted by cheapest price), then single-chain"
    )


class StatsResponse(BaseModel):
    """Database statistics snapshot."""
    chains_count: int
    stores_count: int         = Field(description="Stores with at least one price loaded")
    items_count: int          = Field(description="Distinct barcodes in items table")
    prices_count: int         = Field(description="Total price rows across all stores")
    last_fetch_per_chain: dict[str, str | None] = Field(
        description="chain name → ISO timestamp of last successful fetch"
    )


class ChainFreshness(BaseModel):
    """Last successful load timestamp for one chain."""
    chain_name: str
    last_loaded_at: str | None = Field(None, description="ISO 8601 UTC timestamp of last run with files_loaded > 0")


class FreshnessResponse(BaseModel):
    """Data freshness snapshot across all chains."""
    oldest_last_loaded_at: str | None = Field(None, description="Earliest last_loaded_at across chains that have data")
    chains: list[ChainFreshness]       = Field(description="One entry per chain, sorted oldest-first then nulls")
