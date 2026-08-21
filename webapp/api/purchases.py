"""API endpoints for purchase history: /api/purchases."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Purchase, User
from database.repositories import PurchaseRepository
from webapp.api.deps import get_current_user, get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/purchases", tags=["purchases"])


def _serialize(purchase: Purchase, with_data: bool = False) -> dict:
    """Serialize a purchase for the API."""
    data: dict = {
        "id": purchase.id,
        "item_name": purchase.item_name,
        "price": float(purchase.price),
        "created_at": purchase.created_at.isoformat() if purchase.created_at else None,
    }
    if with_data:
        data["data"] = purchase.product_item.data if purchase.product_item else ""
    return data


@router.get("")
async def list_purchases(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db)
) -> list[dict]:
    """Return the current user's purchases with delivered product data."""
    purchases = await PurchaseRepository(session).list_for_user(user.id)
    return [_serialize(p, with_data=True) for p in purchases]


@router.get("/history")
async def purchase_history(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db)
) -> list[dict]:
    """Return the purchase history WITHOUT product data (for the profile sheet)."""
    purchases = await PurchaseRepository(session).list_for_user(user.id)
    return [_serialize(p, with_data=False) for p in purchases]


@router.get("/{purchase_id}")
async def get_purchase(
    purchase_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Return one purchase including the delivered product data."""
    purchase = await PurchaseRepository(session).get(purchase_id, user.id)
    if purchase is None:
        raise HTTPException(status_code=404, detail="Purchase not found")
    return _serialize(purchase, with_data=True)
