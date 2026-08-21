"""Business logic for products."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Item
from database.repositories import ItemRepository, ProductItemRepository

logger = logging.getLogger(__name__)


class ItemService:
    """Product-related use cases."""

    def __init__(self, session: AsyncSession) -> None:
        self._items = ItemRepository(session)
        self._units = ProductItemRepository(session)

    async def list_items(self, query: str | None = None) -> list[dict]:
        """Return active products with live availability counts.

        Args:
            query: Optional case-insensitive name filter.
        """
        items = await self._items.list_active()
        if query:
            q = query.strip().lower()
            items = [i for i in items if q in i.name.lower()]
        counts = await self._units.counts_for_items([i.id for i in items])
        return [self._serialize(item, counts.get(item.id, 0)) for item in items]

    async def get_item(self, item_id: int) -> dict | None:
        """Return a single active product or ``None``."""
        item = await self._items.get(item_id)
        if item is None or not item.is_active:
            return None
        available = await self._units.count_available(item.id)
        return self._serialize(item, available)

    @staticmethod
    def _serialize(item: Item, available: int) -> dict:
        """Convert an :class:`Item` into a JSON-safe dict."""
        return {
            "id": item.id,
            "name": item.name,
            "description": item.description,
            "price": float(item.price),
            "image_url": item.image_url,
            "stock": available,
            "in_stock": available > 0,
        }
