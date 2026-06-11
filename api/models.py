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


class ChainCoverage(BaseModel):
    """72h per-store coverage for one chain."""
    chain_id: str
    chain_name: str | None
    stores_configured: int  = Field(description="Configured store count from active_stores.yaml")
    stores_loaded_72h: int  = Field(description="Stores with status='loaded' in fetch_store_runs within 72h")
    stores_seen_72h: int    = Field(description="Stores that appeared in fetch_store_runs within 72h (any status)")
    coverage_pct: float     = Field(description="stores_loaded_72h / stores_configured × 100")


class CoverageResponse(BaseModel):
    """Per-store 72h coverage snapshot across all configured chains."""
    chains: list[ChainCoverage] = Field(description="One entry per chain, sorted by coverage_pct ascending (worst first)")


class PromoItem(BaseModel):
    """One active promo row for a store."""
    model_config = ConfigDict(from_attributes=True)

    item_code: str
    promo_id: str | None
    promo_description: str | None
    promo_type: int | None
    allow_multiple_discounts: bool | None
    min_qty: float | None
    reward_type: str | None
    discount_rate: float | None
    discount_price: float | None
    min_purchase_amount: float | None
    promo_start: str | None
    promo_end: str | None
