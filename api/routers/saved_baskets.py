"""Saved baskets endpoints — requires authentication."""
import json
from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import text

from api.auth import get_current_user
from api.dependencies import get_db

router = APIRouter(prefix="/baskets", tags=["Saved Baskets"])


# ---------------------------------------------------------------------------
# Request / response shapes
# ---------------------------------------------------------------------------

class BasketItemIn(BaseModel):
    barcode: str
    name: str
    qty: int


class SaveBasketRequest(BaseModel):
    name: str
    items: list[BasketItemIn]


class UpdateBasketRequest(BaseModel):
    name: Optional[str]  = None
    items: Optional[list[BasketItemIn]] = None


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _owned_or_404(conn, basket_id: int, user_id: str) -> None:
    """Raise 404 if basket doesn't exist or belongs to a different user."""
    row = conn.execute(
        text("SELECT user_id FROM saved_baskets WHERE id = :id"),
        {"id": basket_id},
    ).fetchone()
    if not row or row[0] != user_id:
        raise HTTPException(status_code=404)


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("", status_code=201)
def create_basket(
    body: SaveBasketRequest,
    user=Depends(get_current_user),
    conn=Depends(get_db),
):
    row = conn.execute(text("""
        INSERT INTO saved_baskets (user_id, name, items)
        VALUES (:user_id, :name, CAST(:items AS jsonb))
        RETURNING id, name, items, created_at, updated_at
    """), {
        "user_id": user["id"],
        "name":    body.name,
        "items":   json.dumps([i.model_dump() for i in body.items]),
    }).mappings().fetchone()
    conn.commit()
    return dict(row)


@router.get("")
def list_baskets(user=Depends(get_current_user), conn=Depends(get_db)):
    rows = conn.execute(text("""
        SELECT id, name, updated_at,
               jsonb_array_length(items) AS item_count
        FROM saved_baskets
        WHERE user_id = :user_id
        ORDER BY updated_at DESC
    """), {"user_id": user["id"]}).mappings().all()
    return [dict(r) for r in rows]


@router.get("/{basket_id}")
def get_basket(basket_id: int, user=Depends(get_current_user), conn=Depends(get_db)):
    _owned_or_404(conn, basket_id, user["id"])
    row = conn.execute(text("""
        SELECT id, name, items, created_at, updated_at
        FROM saved_baskets WHERE id = :id
    """), {"id": basket_id}).mappings().fetchone()
    return dict(row)


@router.put("/{basket_id}")
def update_basket(
    basket_id: int,
    body: UpdateBasketRequest,
    user=Depends(get_current_user),
    conn=Depends(get_db),
):
    _owned_or_404(conn, basket_id, user["id"])

    clauses: list[str] = ["updated_at = now()"]
    params: dict = {"id": basket_id}

    if body.name is not None:
        clauses.append("name = :name")
        params["name"] = body.name
    if body.items is not None:
        clauses.append("items = CAST(:items AS jsonb)")
        params["items"] = json.dumps([i.model_dump() for i in body.items])

    row = conn.execute(text(f"""
        UPDATE saved_baskets SET {', '.join(clauses)}
        WHERE id = :id
        RETURNING id, name, items, created_at, updated_at
    """), params).mappings().fetchone()
    conn.commit()
    return dict(row)


@router.delete("/{basket_id}", status_code=204)
def delete_basket(basket_id: int, user=Depends(get_current_user), conn=Depends(get_db)):
    _owned_or_404(conn, basket_id, user["id"])
    conn.execute(text("DELETE FROM saved_baskets WHERE id = :id"), {"id": basket_id})
    conn.commit()
