"""Key-value settings repository (wallet addresses etc.)."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Setting

logger = logging.getLogger(__name__)

# Default wallet addresses; the admin can change them via the API at any time.
DEFAULT_SETTINGS: dict[str, str] = {
    "wallet_btc": "",
    "wallet_eth": "",
    "wallet_usdt_trc20": "",
}


class SettingRepository:
    """Data access layer for :class:`Setting`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def get(self, key: str, default: str = "") -> str:
        """Return a setting value or the default."""
        result = await self._session.execute(select(Setting).where(Setting.key == key))
        row = result.scalar_one_or_none()
        return row.value if row is not None else default

    async def get_many(self, keys: list[str]) -> dict[str, str]:
        """Return values for multiple keys (missing keys resolve to '')."""
        result = await self._session.execute(select(Setting).where(Setting.key.in_(keys)))
        found = {row.key: row.value for row in result.scalars().all()}
        return {key: found.get(key, DEFAULT_SETTINGS.get(key, "")) for key in keys}

    async def set(self, key: str, value: str) -> None:
        """Create or update a setting."""
        result = await self._session.execute(select(Setting).where(Setting.key == key))
        row = result.scalar_one_or_none()
        if row is None:
            self._session.add(Setting(key=key, value=value))
        else:
            row.value = value
        await self._session.flush()
        logger.info("Setting %s updated", key)
