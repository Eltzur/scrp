"""SU11A-77: does a barcode have a product image? (the has_image flag on search,
compare and category results).

The images are files `{gtin}.jpg` in one directory (scraper/gs1_fetch_images.py,
weekly), and nothing in the database records which barcodes have one. So the
set of barcodes with an image is ONE directory listing, cached per process and
refreshed at most every REFRESH_S: a result item costs a set lookup, never a
filesystem call. A new image shows up within REFRESH_S; a removed one may be
reported for that long (the image route then answers 404, as before).

If the directory cannot be listed, has_image answers None ("unknown"), and the
clients behave as before (they may ask for the image).
"""
from __future__ import annotations

import logging
import os
import threading
import time
from pathlib import Path

log = logging.getLogger(__name__)

# The image directory: from the `gs1_images_dir` env var (lowercase, the project
# convention), else ~/gs1_images. api/routers/product.py serves files from it.
IMAGE_DIR = Path(os.environ.get("gs1_images_dir") or (Path.home() / "gs1_images"))
REFRESH_S = 600.0

_lock = threading.Lock()
_state: dict = {"at": None, "codes": None}


def _list(directory: Path) -> frozenset[str]:
    with os.scandir(directory) as it:
        return frozenset(e.name[:-4] for e in it if e.name.endswith(".jpg") and e.is_file())


def image_codes(now: float | None = None, directory: Path | None = None) -> frozenset[str] | None:
    """The barcodes with an image file, or None when the directory cannot be read."""
    t = time.monotonic() if now is None else now
    with _lock:
        at, codes = _state["at"], _state["codes"]
        if at is not None and t - at < REFRESH_S:
            return codes
    try:
        codes = _list(directory or IMAGE_DIR)
    except OSError as exc:
        log.warning("product images unavailable: %s", type(exc).__name__)
        codes = None
    with _lock:
        _state["at"], _state["codes"] = t, codes
    return codes


def has_image(item_code: str) -> bool | None:
    codes = image_codes()
    return None if codes is None else item_code in codes


def reset() -> None:
    """Tests only."""
    with _lock:
        _state["at"], _state["codes"] = None, None
