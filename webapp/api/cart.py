"""API endpoints for the cart: /api/cart."""

import logging

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import User
from services import CartService
from webapp.api.deps import get_current_user, get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cart", tags=["cart"])


class CartAddRequest(BaseModel):
    """Payload for adding an item to the cart."""

    item_id: int = Field(gt=0)
    quantity: int = Field(default=1, ge=1, le=99)


class CartQuantityRequest(BaseModel):
    """Payload for setting an exact quantity."""

    item_id: int = Field(gt=0)
    quantity: int = Field(ge=0, le=99)


@router.get("")
async def get_cart(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db)
) -> dict:
    """Return the current user's cart."""
    return await CartService(session).get_cart(user)


@router.post("/add")
async def add_to_cart(
    payload: CartAddRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Add an item to the cart."""
    try:
        return await CartService(session).add_to_cart(user, payload.item_id, payload.quantity)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/quantity")
async def set_quantity(
    payload: CartQuantityRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Set the exact quantity of a cart row (0 removes it)."""
    try:
        return await CartService(session).set_quantity(user, payload.item_id, payload.quantity)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.delete("/{item_id}")
async def remove_from_cart(
    item_id: int,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Remove an item from the cart."""
    return await CartService(session).remove_from_cart(user, item_id)


@router.post("/checkout")
async def checkout(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db)
) -> dict:
    """Charge the balance and create a purchase from the cart."""
    try:
        return await CartService(session).checkout(user)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
