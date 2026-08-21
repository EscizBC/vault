"""CRUD repository for purchases (delivered digital units)."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from database.models import Purchase

logger = logging.getLogger(__name__)


class PurchaseRepository:
    """Data access layer for :class:`Purchase`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_user(self, user_id: int) -> list[Purchase]:
        """Return purchases for a user with delivered unit data, newest first."""
        result = await self._session.execute(
            select(Purchase)
            .where(Purchase.user_id == user_id)
            .options(selectinload(Purchase.product_item))
            .order_by(Purchase.id.desc())
        )
        return list(result.scalars().all())

    async def get(self, purchase_id: int, user_id: int) -> Purchase | None:
        """Return a purchase belonging to the user or ``None``."""
        result = await self._session.execute(
            select(Purchase)
            .where(Purchase.id == purchase_id, Purchase.user_id == user_id)
            .options(selectinload(Purchase.product_item))
        )
        return result.scalar_one_or_none()

    async def create(
        self,
        user_id: int,
        item_id: int,
        product_item_id: int,
        item_name: str,
        price: float,
    ) -> Purchase:
        """Create a purchase record for one delivered unit."""
        purchase = Purchase(
            user_id=user_id,
            item_id=item_id,
            product_item_id=product_item_id,
            item_name=item_name,
            price=price,
        )
        self._session.add(purchase)
        await self._session.flush()
        logger.info(
            "Created purchase id=%s user=%s item=%s unit=%s price=%.2f",
            purchase.id, user_id, item_id, product_item_id, price,
        )
        return purchase
