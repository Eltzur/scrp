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
    reward_type: int | None
    discount_rate: float | None
    discount_price: float | None
    min_purchase_amount: float | None
    promo_start: str | None
    promo_end: str | None
    discount_pct: float | None


class HotPromoItem(BaseModel):
    """One hot-deal promo row returned by GET /promos/today."""
    model_config = ConfigDict(from_attributes=True)

    item_code: str
    promo_description: str | None
    discount_pct: float | None
    item_price: float | None
    discount_price: float | None
    min_qty: float | None
    reward_type: int | None
    chain_name: str | None
    store_name: str | None
    city: str | None
    promo_end: str | None


class KashrutInfo(BaseModel):
    """Kosher certification block from GS1. Every field is optional — suppliers
    fill this in very unevenly, and a blank field means 'not declared', not 'no'."""
    model_config = ConfigDict(from_attributes=True)

    supervision_type: str | None    = Field(None, description="e.g. בשרי / חלבי / פרווה")
    rabbinate: list[str]            = Field(default_factory=list, description="Certifying rabbinate(s)")
    board: list[str]                = Field(default_factory=list, description="Board of supervision (בד\"ץ etc.)")
    kosher_for_passover: str | None = None
    passover_remark: str | None     = None
    israel_milk: str | None         = Field(None, description="חלב ישראל")
    cooking_israel: str | None      = Field(None, description="בישול ישראל")
    sabbath_observing: str | None   = Field(None, description="מפעל שומר שבת")
    sheviit_orlah_tevel: str | None = None


class NutritionRow(BaseModel):
    """One line of the nutrition panel."""
    model_config = ConfigDict(from_attributes=True)

    label: str | None = Field(None, description="e.g. אנרגיה (קלוריות)")
    value: str | None = Field(None, description="Raw numeric string; may be a GS1 code like 'L 0.5'")
    uom: str | None   = Field(None, description="Unit of measure")
    text: str | None  = Field(None, description="Supplier's own rendering — prefer this for display; it is the only form that survives non-numeric declarations such as 'פחות מ-0.5 גרם'")


class NutritionTable(BaseModel):
    """Nutrition panel. Absent for ~1/3 of products that publish none."""
    model_config = ConfigDict(from_attributes=True)

    basis: str | None       = Field(None, description="Measurement basis, e.g. ל-100 גרם")
    rows: list[NutritionRow] = Field(default_factory=list)


class AllergenInfo(BaseModel):
    """Coded allergen declarations."""
    model_config = ConfigDict(from_attributes=True)

    contains: list[str]    = Field(default_factory=list, description="Declared allergens")
    may_contain: list[str] = Field(default_factory=list, description="Trace / shared-line warnings")


class ProductDetails(BaseModel):
    """GS1 enrichment detail for one item_code.

    ALWAYS returns 200 with this shape for a known item_code. Only ~8% of items
    have a GS1 match, so `has_gs1_data: false` is the ordinary case and carries
    no error — the client should render name + prices and omit the rest.
    """
    model_config = ConfigDict(from_attributes=True)

    item_code: str
    has_gs1_data: bool             = Field(description="False for the ~92% of items with no active GS1 match")
    has_image: bool                = Field(description="True if GET /product/{item_code}/image will return a JPEG")
    gtin: str | None               = None
    brand: str | None              = None
    gs1_name: str | None           = Field(None, description="GS1 trade_item_description")
    category: str | None           = None
    kashrut: KashrutInfo | None    = None
    nutrition: NutritionTable | None = None
    ingredients: str | None        = Field(None, description="Full ingredient string, incl. percentages")
    allergens: AllergenInfo | None = None


class GroupedPromoItem(BaseModel):
    """One promo row for the chain -> city -> branch display.

    Flat by design: the frontend groups by chain -> city -> branch. Unlike
    /promos/today these are NOT deduplicated, so the same item_code appears once
    per branch — that per-branch granularity is the point of the view.
    """
    model_config = ConfigDict(from_attributes=True)

    chain_id: str
    chain_name: str | None
    city: str | None            = Field(None, description="stores.city_canonical; may be NULL for a few stores")
    branch: str | None          = Field(None, description="stores.store_name")
    store_fk: int               = Field(description="stores.id — pass back as ?branch= to filter to this branch")
    item_code: str
    product_name: str | None    = Field(None, description="Canonical items.item_name; NULL if the promo item is not in our catalog")
    shelf_price: float | None   = Field(None, description="Current shelf price at this store; NULL when we hold no price row (~18%)")
    min_qty: float | None       = Field(None, description="Units required for the bundle price")
    promo_kind: str             = Field("unit", description="'unit' = has a per-unit price; 'basket' = conditional/spend-threshold deal with no derivable unit price")
    promo_type: str | None      = Field(None, description="Shape-derived class: gift | bundle | fixed | discount | basket. Derived from the numbers, NOT from reward_type (which is chain-specific)")
    savings: float | None       = Field(None, description="shelf_price - unit_price in shekels; NULL for basket rows")
    min_purchase_amount: float | None = Field(None, description="Minimum spend condition as published; NULL when the promo has none")
    discount_price: float | None = Field(None, description="Raw DiscountedPrice — a BUNDLE TOTAL, not per unit")
    reward_type: int | None     = Field(None, description="Source RewardType; 1 = buy-one-get-one, where discount_price=0 marks the free item rather than a 100% discount")
    unit_price: float | None    = Field(None, description="discount_price / min_qty — the per-unit figure to compare against shelf_price")
    discount_pct: float | None  = Field(None, description="Rounded % off shelf_price; NULL when shelf_price is unknown")
    promo_description: str | None
    promo_start: str | None
    promo_end: str | None
