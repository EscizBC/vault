"""Business logic for the admin panel."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from database.models import TransactionType, User
from database.repositories import (
    ItemRepository,
    ProductItemRepository,
    SettingRepository,
    TransactionRepository,
    UserRepository,
)

logger = logging.getLogger(__name__)


class AdminService:
    """Admin use cases: restock, visibility, balance adjustments, settings."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._items = ItemRepository(session)
        self._units = ProductItemRepository(session)
        self._users = UserRepository(session)
        self._transactions = TransactionRepository(session)
        self._settings = SettingRepository(session)

    async def list_products(self) -> list[dict]:
        """Return every product (including hidden) with availability counts."""
        items = await self._items.list_all()
        counts = await self._units.counts_for_items([i.id for i in items])
        return [
            {
                "id": item.id,
                "name": item.name,
                "description": item.description,
                "price": float(item.price),
                "image_url": item.image_url,
                "is_active": item.is_active,
                "stock": counts.get(item.id, 0),
            }
            for item in items
        ]

    async def restock(
        self,
        name: str,
        description: str,
        price: float | None,
        image_url: str,
        units: list[str],
        item_id: int | None = None,
    ) -> dict:
        """Create a product or add units to an existing one.

        Per the spec: if an existing product is chosen, its description is
        reused (and may be updated). New products require a price.

        Raises:
            ValueError: On invalid input.
        """
        units = [u for u in units if u.strip()]
        if item_id is not None:
            item = await self._items.get(item_id)
            if item is None:
                raise ValueError("Товар не найден")
            if description.strip():
                item.description = description.strip()
            if price is not None and price > 0:
                item.price = price
            if image_url.strip():
                item.image_url = image_url.strip()
        else:
            if not name.strip():
                raise ValueError("Введите название товара")
            existing = await self._items.find_by_name(name)
            if existing is not None:
                item = existing
                if description.strip():
                    item.description = description.strip()
                if price is not None and price > 0:
                    item.price = price
                if image_url.strip():
                    item.image_url = image_url.strip()
            else:
                if price is None or price <= 0:
                    raise ValueError("Укажите цену нового товара")
                item = await self._items.create(
                    name=name.strip(),
                    description=description.strip(),
                    price=price,
                    image_url=image_url.strip(),
                )
        added = await self._units.add_units(item.id, units)
        available = await self._units.count_available(item.id)
        return {"item_id": item.id, "added": len(added), "stock": available}

    async def set_visibility(self, item_id: int, visible: bool) -> dict:
        """Hide or show a product. Existing purchases are untouched.

        Raises:
            ValueError: If the product does not exist.
        """
        item = await self._items.get(item_id)
        if item is None:
            raise ValueError("Товар не найден")
        await self._items.set_visibility(item, visible)
        return {"item_id": item.id, "is_active": item.is_active}

    async def adjust_balance(
        self, admin: User, telegram_id: int, amount: float, action: str, comment: str
    ) -> dict:
        """Credit or debit a user's balance with a mandatory history record.

        Raises:
            ValueError: On invalid input or unknown user.
        """
        amount = round(float(amount), 2)
        if amount <= 0:
            raise ValueError("Сумма должна быть больше нуля")
        if action not in ("credit", "debit"):
            raise ValueError("Неизвестное действие")
        target = await self._users.get_by_telegram_id(telegram_id)
        if target is None:
            raise ValueError("Пользователь не найден")
        if action == "credit":
            await self._users.add_balance(target, amount)
            signed = amount
        else:
            await self._users.deduct_balance(target, amount)
            signed = -amount
        await self._transactions.create(
            user_id=target.id,
            type_=TransactionType.ADMIN_ADJUST,
            amount=signed,
            payment_method="admin",
            comment=comment.strip() or f"Balance adjusted by admin @{admin.username or admin.telegram_id}",
        )
        logger.info(
            "Admin %s adjusted balance of %s by %+.2f",
            admin.telegram_id, telegram_id, signed,
        )
        return {"telegram_id": telegram_id, "balance": float(target.balance)}

    async def find_user(self, query: str) -> dict | None:
        """Find a user by Telegram ID or @username."""
        user = None
        q = query.strip().lstrip("@")
        if q.isdigit():
            user = await self._users.get_by_telegram_id(int(q))
        if user is None and q:
            from sqlalchemy import select

            from database.models import User as UserModel

            result = await self._session.execute(
                select(UserModel).where(UserModel.username.ilike(q))
            )
            user = result.scalars().first()
        if user is None:
            return None
        return {
            "telegram_id": user.telegram_id,
            "username": user.username,
            "first_name": user.first_name,
            "balance": float(user.balance),
        }

    async def update_wallets(self, wallets: dict[str, str]) -> None:
        """Update deposit wallet addresses stored in settings."""
        from services.payment_service import WALLET_KEYS

        for key, value in wallets.items():
            if key in WALLET_KEYS:
                await self._settings.set(key, value.strip())
