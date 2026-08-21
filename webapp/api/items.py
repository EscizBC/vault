"""API endpoints for products: /api/items."""

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession

from services import ItemService
from webapp.api.deps import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/items", tags=["items"])


@router.get("")
async def list_items(
    q: str | None = Query(default=None, max_length=128),
    session: AsyncSession = Depends(get_db),
) -> list[dict]:
    """Return active products, optionally filtered by name."""
    return await ItemService(session).list_items(query=q)


@router.get("/{item_id}")
async def get_item(item_id: int, session: AsyncSession = Depends(get_db)) -> dict:
    """Return a single product by ID."""
    item = await ItemService(session).get_item(item_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Product not found")
    return item
