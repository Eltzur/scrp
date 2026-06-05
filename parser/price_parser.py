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
                "manufacturer_name":     _text(el, "ManufacturerName"),
                "manufacture_country":   _text(el, "ManufactureCountry"),
                "unit_qty":              _text(el, "UnitQty"),
                "quantity":              _real(el, "Quantity"),
                "is_weighted":           _int(el,  "bIsWeighted"),
                "unit_of_measure":       _text(el, "UnitOfMeasure"),
                "qty_in_package":        _int(el,  "QtyInPackage"),
                "price_update_date":     _text(el, "PriceUpdateDate"),
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
