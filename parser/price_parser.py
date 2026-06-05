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
    Parse a Promo or PromoFull XML file.
    Returns (header, items_generator).
    Each yielded dict is one (promo × item_code) pair with all promo fields.
    Handles both 'Sale' (Shufersal/Cerberus) and 'Promotion' element names.
    """
    tree = etree.parse(str(path))
    root = tree.getroot()

    header = {
        "chain_id":     (root.findtext("ChainId") or "").strip(),
        "sub_chain_id": (root.findtext("SubChainId") or "").strip(),
        "store_id":     (root.findtext("StoreId") or "").strip(),
    }

    def _items():
        for promo_el in root.iter():
            if promo_el.tag not in ("Sale", "Promotion"):
                continue
            promo_id    = _text(promo_el, "PromotionId")
            description = _text(promo_el, "PromotionDescription")
            promo_type  = _int(promo_el,  "PromotionType")
            allow_multi = _int(promo_el,  "AllowMultipleDiscounts")
            min_qty     = _real(promo_el, "MinQty")
            reward_type = _int(promo_el,  "RewardType")
            disc_rate   = _real(promo_el, "DiscountRate")
            disc_price  = _real(promo_el, "DiscountedPrice")
            min_purch   = _real(promo_el, "MinPurchaseAmnt")
            start_date  = _text(promo_el, "PromotionStartDate")
            end_date    = _text(promo_el, "PromotionEndDate")

            items_el = promo_el.find("Items") or promo_el.find("PromotionItems")
            if items_el is None:
                continue
            for item_el in items_el:
                item_code = _text(item_el, "ItemCode") or _text(item_el, "Barcode")
                if not item_code:
                    continue
                yield {
                    "item_code":                item_code,
                    "promo_id":                 promo_id,
                    "promo_description":        description,
                    "promo_type":               promo_type,
                    "allow_multiple_discounts": bool(allow_multi) if allow_multi is not None else None,
                    "min_qty":                  min_qty,
                    "reward_type":              reward_type,
                    "discount_rate":            disc_rate,
                    "discount_price":           disc_price,
                    "min_purchase_amount":      min_purch,
                    "promo_start":              start_date,
                    "promo_end":                end_date,
                }

    return header, _items()
