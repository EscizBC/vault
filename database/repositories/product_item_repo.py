"""CRUD repository for digital product units (ProductItem)."""

import logging

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import ProductItem, ProductItemStatus, utcnow

logger = logging.getLogger(__name__)


class ProductItemRepository:
    """Data access layer for :class:`ProductItem`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def count_available(self, item_id: int) -> int:
        """Return the number of available units for a product."""
        result = await self._session.execute(
            select(func.count(ProductItem.id)).where(
                ProductItem.item_id == item_id,
                ProductItem.status == ProductItemStatus.AVAILABLE,
            )
        )
        return int(result.scalar_one())

    async def counts_for_items(self, item_ids: list[int]) -> dict[int, int]:
        """Return ``{item_id: available_count}`` for the given products."""
        if not item_ids:
            return {}
        result = await self._session.execute(
            select(ProductItem.item_id, func.count(ProductItem.id))
            .where(
                ProductItem.item_id.in_(item_ids),
                ProductItem.status == ProductItemStatus.AVAILABLE,
            )
            .group_by(ProductItem.item_id)
        )
        return {row[0]: int(row[1]) for row in result.all()}

    async def reserve_one(self, item_id: int) -> ProductItem | None:
        """Atomically reserve one available unit (row-locked within the transaction).

        Returns ``None`` when no unit is available.
        """
        stmt = (
            select(ProductItem)
            .where(
                ProductItem.item_id == item_id,
                ProductItem.status == ProductItemStatus.AVAILABLE,
            )
            .order_by(ProductItem.id)
            .limit(1)
        )
        # SQLite does not support FOR UPDATE; PostgreSQL uses it to prevent
        # two concurrent checkouts from grabbing the same unit.
        if self._session.bind is not None and self._session.bind.dialect.name == "postgresql":
            stmt = stmt.with_for_update(skip_locked=True)
        result = await self._session.execute(stmt)
        unit = result.scalar_one_or_none()
        if unit is None:
            return None
        unit.status = ProductItemStatus.RESERVED
        await self._session.flush()
        return unit

    async def mark_sold(self, unit: ProductItem, buyer_id: int) -> ProductItem:
        """Mark a reserved unit as sold to the buyer."""
        unit.status = ProductItemStatus.SOLD
        unit.buyer_id = buyer_id
        unit.sold_at = utcnow()
        await self._session.flush()
        logger.info("Unit %s sold to user %s", unit.id, buyer_id)
        return unit

    async def release(self, unit: ProductItem) -> ProductItem:
        """Return a reserved unit back to the available pool."""
        unit.status = ProductItemStatus.AVAILABLE
        unit.buyer_id = None
        unit.sold_at = None
        await self._session.flush()
        return unit

    async def add_units(self, item_id: int, data_list: list[str]) -> list[ProductItem]:
        """Add new available units for a product."""
        units = [ProductItem(item_id=item_id, data=data) for data in data_list if data.strip()]
        self._session.add_all(units)
        await self._session.flush()
        logger.info("Added %d units to item %s", len(units), item_id)
        return units

    async def get(self, unit_id: int) -> ProductItem | None:
        """Return a unit by ID or ``None``."""
        result = await self._session.execute(
            select(ProductItem).where(ProductItem.id == unit_id)
        )
        return result.scalar_one_or_none()
