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
