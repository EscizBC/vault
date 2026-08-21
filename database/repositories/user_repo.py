"""CRUD repository for users."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import User, UserRole

logger = logging.getLogger(__name__)


class UserRepository:
    """Data access layer for :class:`User`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get_by_telegram_id(self, telegram_id: int) -> User | None:
        """Return a user by Telegram ID or ``None``."""
        result = await self._session.execute(select(User).where(User.telegram_id == telegram_id))
        return result.scalar_one_or_none()

    async def get_by_id(self, user_id: int) -> User | None:
        """Return a user by internal ID or ``None``."""
        result = await self._session.execute(select(User).where(User.id == user_id))
        return result.scalar_one_or_none()

    async def list_all_telegram_ids(self) -> list[int]:
        """Return Telegram IDs of every registered user (for broadcasts)."""
        result = await self._session.execute(select(User.telegram_id))
        return [int(x) for x in result.scalars().all()]

    async def get_or_create(
        self,
        telegram_id: int,
        username: str | None = None,
        first_name: str = "",
        avatar_url: str = "",
        is_admin: bool = False,
    ) -> User:
        """Return an existing user or create a new one, refreshing profile data."""
        user = await self.get_by_telegram_id(telegram_id)
        if user is None:
            user = User(
                telegram_id=telegram_id,
                username=username,
                first_name=first_name,
                avatar_url=avatar_url,
                role=UserRole.ADMIN if is_admin else UserRole.USER,
            )
            self._session.add(user)
            await self._session.flush()
            logger.info("Created user telegram_id=%s admin=%s", telegram_id, is_admin)
        else:
            if username and user.username != username:
                user.username = username
            if first_name and user.first_name != first_name:
                user.first_name = first_name
            if avatar_url and user.avatar_url != avatar_url:
                user.avatar_url = avatar_url
            # Keep the admin role in sync with the ADMIN_IDS env var.
            if is_admin and user.role != UserRole.ADMIN:
                user.role = UserRole.ADMIN
        return user

    async def add_balance(self, user: User, amount: float) -> User:
        """Increase the user's balance by ``amount``."""
        user.balance = round(float(user.balance) + amount, 2)
        await self._session.flush()
        logger.info(
            "Balance +%.2f for user %s (new balance %.2f)",
            amount, user.telegram_id, user.balance,
        )
        return user

    async def deduct_balance(self, user: User, amount: float) -> User:
        """Decrease the user's balance by ``amount``.

        Raises:
            ValueError: If the balance is insufficient.
        """
        if float(user.balance) < amount:
            raise ValueError("Insufficient balance")
        user.balance = round(float(user.balance) - amount, 2)
        await self._session.flush()
        logger.info("Balance -%.2f for user %s", amount, user.telegram_id)
        return user
