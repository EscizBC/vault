"""CRUD repository for shop items (products)."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Item

logger = logging.getLogger(__name__)


class ItemRepository:
    """Data access layer for :class:`Item`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_active(self) -> list[Item]:
        """Return all active items."""
        result = await self._session.execute(
            select(Item).where(Item.is_active.is_(True)).order_by(Item.id)
        )
        return list(result.scalars().all())

    async def list_all(self) -> list[Item]:
        """Return all items including hidden ones (admin view)."""
        result = await self._session.execute(select(Item).order_by(Item.id))
        return list(result.scalars().all())

    async def get(self, item_id: int) -> Item | None:
        """Return an item by ID or ``None``."""
        result = await self._session.execute(select(Item).where(Item.id == item_id))
        return result.scalar_one_or_none()

    async def find_by_name(self, name: str) -> Item | None:
        """Return an item with the exact (case-insensitive) name or ``None``."""
        result = await self._session.execute(
            select(Item).where(Item.name.ilike(name.strip()))
        )
        return result.scalars().first()

    async def create(
        self, name: str, description: str, price: float, image_url: str = ""
    ) -> Item:
        """Create a new item."""
        item = Item(name=name, description=description, price=price, image_url=image_url)
        self._session.add(item)
        await self._session.flush()
        logger.info("Created item id=%s name=%s", item.id, name)
        return item

    async def set_visibility(self, item: Item, visible: bool) -> Item:
        """Show or hide an item in the storefront."""
        item.is_active = visible
        await self._session.flush()
        logger.info("Item id=%s visibility=%s", item.id, visible)
        return item
