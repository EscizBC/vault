"""CRUD repository for cart items."""

import logging

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import CartItem

logger = logging.getLogger(__name__)

MAX_QTY_PER_ITEM = 99


class CartRepository:
    """Data access layer for :class:`CartItem`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_user(self, user_id: int) -> list[CartItem]:
        """Return all cart items for a user with related items loaded."""
        result = await self._session.execute(
            select(CartItem)
            .where(CartItem.user_id == user_id)
            .options(selectinload(CartItem.item))
            .order_by(CartItem.id)
        )
        return list(result.scalars().all())

    async def get(self, user_id: int, item_id: int) -> CartItem | None:
        """Return a cart row for the given user and item or ``None``."""
        result = await self._session.execute(
            select(CartItem).where(CartItem.user_id == user_id, CartItem.item_id == item_id)
        )
        return result.scalar_one_or_none()

    async def add(self, user_id: int, item_id: int, quantity: int = 1) -> CartItem:
        """Add an item to the cart or increase its quantity."""
        row = await self.get(user_id, item_id)
        if row is None:
            row = CartItem(user_id=user_id, item_id=item_id, quantity=min(quantity, MAX_QTY_PER_ITEM))
            self._session.add(row)
        else:
            row.quantity = min(row.quantity + quantity, MAX_QTY_PER_ITEM)
        await self._session.flush()
        logger.info("Cart add user=%s item=%s qty=%s", user_id, item_id, row.quantity)
        return row

    async def set_quantity(self, user_id: int, item_id: int, quantity: int) -> CartItem | None:
        """Set the exact quantity; removes the row when quantity <= 0."""
        row = await self.get(user_id, item_id)
        if row is None:
            return None
        if quantity <= 0:
            await self._session.delete(row)
            await self._session.flush()
            return None
        row.quantity = min(quantity, MAX_QTY_PER_ITEM)
        await self._session.flush()
        return row

    async def remove(self, user_id: int, item_id: int) -> None:
        """Remove an item from the cart."""
        await self._session.execute(
            delete(CartItem).where(CartItem.user_id == user_id, CartItem.item_id == item_id)
        )
        await self._session.flush()
        logger.info("Cart remove user=%s item=%s", user_id, item_id)

    async def clear(self, user_id: int) -> None:
        """Remove all items from the user's cart."""
        await self._session.execute(delete(CartItem).where(CartItem.user_id == user_id))
        await self._session.flush()
        logger.info("Cart cleared user=%s", user_id)
