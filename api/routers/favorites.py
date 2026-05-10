"""Favorites endpoints — requires authentication.

Composite PK (user_id, barcode) means all queries are inherently
scoped to the current user — no separate ownership check needed.
"""
from fastapi import APIRouter, Depends
from sqlalchemy import text

from api.auth import get_current_user
from api.dependencies import get_db

router = APIRouter(prefix="/favorites", tags=["Favorites"])


@router.post("/{barcode}")
def toggle_favorite(barcode: str, user=Depends(get_current_user), conn=Depends(get_db)):
    """Toggle: add if not favorited, remove if already favorited.
    Returns {"favorited": bool} reflecting the new state."""
    row = conn.execute(
        text("SELECT 1 FROM favorites WHERE user_id = :uid AND barcode = :bc"),
        {"uid": user["id"], "bc": barcode},
    ).fetchone()

    if row:
        conn.execute(
            text("DELETE FROM favorites WHERE user_id = :uid AND barcode = :bc"),
            {"uid": user["id"], "bc": barcode},
        )
        conn.commit()
        return {"favorited": False}

    conn.execute(
        text("INSERT INTO favorites (user_id, barcode) VALUES (:uid, :bc) ON CONFLICT DO NOTHING"),
        {"uid": user["id"], "bc": barcode},
    )
    conn.commit()
    return {"favorited": True}


@router.get("")
def list_favorites(user=Depends(get_current_user), conn=Depends(get_db)):
    """List all favorited barcodes with canonical name from items table."""
    rows = conn.execute(text("""
        SELECT f.barcode, i.item_name, f.created_at
        FROM favorites f
        LEFT JOIN items i ON i.item_code = f.barcode
        WHERE f.user_id = :uid
        ORDER BY f.created_at DESC
    """), {"uid": user["id"]}).mappings().all()
    return [dict(r) for r in rows]


@router.delete("/{barcode}", status_code=204)
def remove_favorite(barcode: str, user=Depends(get_current_user), conn=Depends(get_db)):
    """Explicitly remove a barcode from favorites (no-op if not present)."""
    conn.execute(
        text("DELETE FROM favorites WHERE user_id = :uid AND barcode = :bc"),
        {"uid": user["id"], "bc": barcode},
    )
    conn.commit()
