"""Parse a Prices / PricesFull XML file into plain dicts."""
from pathlib import Path
from typing import Iterator
from lxml import etree


def _text(el, tag: str, default=None):
    child = el.find(tag)
    if child is None or child.text is None:
        return default
    return child.text.strip()


def _real(el, tag: str):
    v = _text(el, tag)
    try:
        return float(v) if v is not None else None
    except ValueError:
        return None


def _int(el, tag: str):
    v = _text(el, tag)
    try:
        return int(v) if v is not None else None
    except ValueError:
        return None


def parse_file(path: Path) -> tuple:
    """
    Returns (header, items_iter).
    header keys: chain_id, sub_chain_id, store_id
    Each item dict has keys matching the db columns.
    """
    tree = etree.parse(str(path))
    root = tree.getroot()

    header = {
        "chain_id":     (root.findtext("ChainId") or "").strip(),
        "sub_chain_id": (root.findtext("SubChainId") or "").strip(),
        "store_id":     (root.findtext("StoreId") or "").strip(),
    }

    def _items():
        for el in root.iter("Item"):
            yield {
                "item_code":             _text(el, "ItemCode"),
                "item_type":             _int(el,  "ItemType"),
                "item_name":             _text(el, "ItemName"),
                "manufacturer_name":     _first_text(el, "ManufacturerName", "ManufactureName"),
                "manufacture_country":   _text(el, "ManufactureCountry"),
                "unit_qty":              _text(el, "UnitQty"),
                "quantity":              _real(el, "Quantity"),
                "is_weighted":           _int(el,  "bIsWeighted"),
                "unit_of_measure":       _text(el, "UnitOfMeasure"),
                "qty_in_package":        _int(el,  "QtyInPackage"),
                "price_update_date":     _first_text(el, "PriceUpdateDate", "PriceUpdateTime"),
                "item_price":            _real(el, "ItemPrice"),
                "unit_of_measure_price": _real(el, "UnitOfMeasurePrice"),
                "allow_discount":        _int(el,  "AllowDiscount"),
                "item_status":           _int(el,  "ItemStatus"),
            }

    return header, _items()


def parse_promo_file(path: Path) -> tuple:
    """
    Parse a Promo or PromoFull XML file (nested structure).
    Returns (header, items_generator).
    Yields one dict per PromotionItem, with promo fields pulled from the
    parent Promotion and Group elements.

    Structure:
      Root > Promotions > Promotion > Groups > Group > PromotionItems > PromotionItem
    """
    tree = etree.parse(str(path))
    root = tree.getroot()

    header = {
        "chain_id":     (root.findtext("ChainID") or root.findtext("ChainId") or "").strip(),
        "sub_chain_id": (root.findtext("SubChainID") or root.findtext("SubChainId") or "").strip(),
        "store_id":     (root.findtext("StoreID") or root.findtext("StoreId") or "").strip(),
    }

    def _parse_dt(val):
        if not val:
            return None
        return val.split('.')[0] if val else None

    def _items():
        for promo_el in root.iter("Promotion"):
            promo_id    = _text(promo_el, "PromotionID")
            description = _text(promo_el, "PromotionDescription")
            allow_multi = _int(promo_el,  "AllowMultipleDiscounts")
            start_dt    = _parse_dt(_text(promo_el, "PromotionStartDateTime"))
            end_dt      = _parse_dt(_text(promo_el, "PromotionEndDateTime"))

            for group_el in promo_el.iter("Group"):
                min_purch = _real(group_el, "MinPurchaseAmount")

                for item_el in group_el.iter("PromotionItem"):
                    item_code = _text(item_el, "ItemCode")
                    if not item_code:
                        continue
                    yield {
                        "item_code":                item_code,
                        "promo_id":                 promo_id,
                        "promo_description":        description,
                        "allow_multiple_discounts": allow_multi,
                        "promo_start":              start_dt,
                        "promo_end":                end_dt,
                        "min_purchase_amount":      min_purch,
                        "reward_type":              _int(item_el,  "RewardType"),
                        "min_qty":                  _real(item_el, "MinQty"),
                        "discount_rate":            _real(item_el, "DiscountRate"),
                        "discount_price":           _real(item_el, "DiscountedPrice"),
                    }

    return header, _items()


# ---------------------------------------------------------------------------
# Flat-variant promo parser (BinaProjects + Hazi Hinam)
# ---------------------------------------------------------------------------
#
# These two portals publish a DIFFERENT promo shape from the four that
# parse_promo_file() handles. Confirmed from live files in SU10A-5 recon:
#
#   * no <Groups>/<Group> level at all;
#   * items are <Item><ItemCode>, not <PromotionItem>;
#   * every discount field lives on <Promotion>, so all items under one
#     promotion INHERIT the same price/qty rather than carrying their own;
#   * dates are split into <...Date> + <...Hour> instead of one DateTime.
#
# Feeding these files to parse_promo_file() yields ZERO rows silently — the
# Group loop never enters — which is exactly why King Store, Shefa, Shuk Hayir
# and Hazi Hinam had no promos at all. It is a separate function on purpose:
# the ten working chains depend on parse_promo_file() unchanged.

def _first_text(el, *tags, default=None):
    """First non-empty value among several spellings of the same field.

    The two portals disagree on casing and spelling for identical fields
    (PromotionId/PromotionID, MinPurchaseAmnt/MinPurchaseAmount), so every
    lookup accepts the known variants rather than guessing per chain.
    """
    for tag in tags:
        v = _text(el, tag)
        if v not in (None, ""):
            return v
    return default


def _first_real(el, *tags):
    v = _first_text(el, *tags)
    if v is None:
        return None
    try:
        return float(v)
    except ValueError:
        return None


def _first_int(el, *tags):
    v = _first_text(el, *tags)
    if v is None:
        return None
    try:
        return int(float(v))  # some fields arrive as "1.00"
    except ValueError:
        return None


def _join_dt(date_val: str | None, hour_val: str | None) -> str | None:
    """Combine split date + hour into one 'YYYY-MM-DD HH:MM:SS' stamp."""
    if not date_val:
        return None
    date_val = date_val.strip()
    hour_val = (hour_val or "").strip()
    if not hour_val:
        return date_val
    # Some files already carry a full datetime in the date field.
    if " " in date_val or "T" in date_val:
        return date_val.replace("T", " ").split(".")[0]
    return f"{date_val} {hour_val.split('.')[0]}"


def parse_promo_file_flat(path: Path) -> tuple:
    """Parse a flat-variant Promo/PromoFull file (BinaProjects, Hazi Hinam).

    Returns (header, items_generator) — same contract as parse_promo_file, so
    callers and bulk_insert_promos need no special casing.

    Emits one row per <Item>, carrying the parent <Promotion>'s discount fields
    down onto each row. That fan-out is inherent to the format: a single Bina
    promotion can list 872 items, and each is a real promoted product.
    """
    tree = etree.parse(str(path))
    root = tree.getroot()

    header = {
        "chain_id":     (_first_text(root, "ChainID", "ChainId") or "").strip(),
        "sub_chain_id": (_first_text(root, "SubChainID", "SubChainId") or "").strip(),
        "store_id":     (_first_text(root, "StoreID", "StoreId") or "").strip(),
    }

    def _items():
        for promo_el in root.iter("Promotion"):
            promo_id    = _first_text(promo_el, "PromotionId", "PromotionID")
            description = _first_text(promo_el, "PromotionDescription")
            # DiscountType finally gives promos.promo_type a value; the shared
            # parser never populated that column for any chain.
            promo_type  = _first_int(promo_el,  "DiscountType")
            allow_multi = _first_int(promo_el,  "AllowMultipleDiscounts")
            reward_type = _first_int(promo_el,  "RewardType")
            min_qty     = _first_real(promo_el, "MinQty")
            disc_rate   = _first_real(promo_el, "DiscountRate")
            disc_price  = _first_real(promo_el, "DiscountedPrice")
            min_purch   = _first_real(promo_el, "MinPurchaseAmnt", "MinPurchaseAmount")
            start_dt    = _join_dt(_first_text(promo_el, "PromotionStartDate"),
                                   _first_text(promo_el, "PromotionStartHour"))
            end_dt      = _join_dt(_first_text(promo_el, "PromotionEndDate"),
                                   _first_text(promo_el, "PromotionEndHour"))

            # Only real promoted items — GiftsItems is a sibling container and
            # its entries are not products the shopper is buying at this price.
            for items_el in promo_el.findall("PromotionItems"):
                for item_el in items_el.iter("Item"):
                    item_code = _text(item_el, "ItemCode")
                    if not item_code:
                        continue
                    yield {
                        "item_code":                item_code,
                        "promo_id":                 promo_id,
                        "promo_description":        description,
                        "promo_type":               promo_type,
                        "allow_multiple_discounts": allow_multi,
                        "promo_start":              start_dt,
                        "promo_end":                end_dt,
                        "min_purchase_amount":      min_purch,
                        "reward_type":              reward_type,
                        "min_qty":                  min_qty,
                        "discount_rate":            disc_rate,
                        "discount_price":           disc_price,
                    }

    return header, _items()
