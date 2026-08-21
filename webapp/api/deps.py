"""Shared FastAPI dependencies: DB session and Telegram WebApp authentication."""

import hashlib
import hmac
import json
import logging
from collections.abc import AsyncGenerator
from urllib.parse import parse_qsl

from fastapi import Depends, Header, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database.db import async_session_factory
from database.models import User, UserRole
from database.repositories import UserRepository

logger = logging.getLogger(__name__)


async def get_db() -> AsyncGenerator[AsyncSession, None]:
    """Yield a request-scoped async DB session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


def _validate_init_data(init_data: str, bot_token: str) -> dict | None:
    """Validate Telegram WebApp ``initData`` signature.

    Returns the parsed user dict on success, ``None`` on failure.
    """
    try:
        pairs = dict(parse_qsl(init_data, keep_blank_values=True))
        received_hash = pairs.pop("hash", "")
        data_check_string = "\n".join(f"{k}={v}" for k, v in sorted(pairs.items()))
        secret_key = hmac.new(b"WebAppData", bot_token.encode(), hashlib.sha256).digest()
        calculated_hash = hmac.new(secret_key, data_check_string.encode(), hashlib.sha256).hexdigest()
        if not hmac.compare_digest(calculated_hash, received_hash):
            return None
        return json.loads(pairs.get("user", "{}"))
    except (ValueError, KeyError) as exc:
        logger.warning("initData validation failed: %s", exc)
        return None


async def get_current_user(
    session: AsyncSession = Depends(get_db),
    authorization: str | None = Header(default=None),
) -> User:
    """Authenticate the request via Telegram WebApp initData.

    Expects ``Authorization: tma <initData>``. When ``BOT_TOKEN`` is not
    configured (local development), a demo admin user is used so the SPA can
    be previewed outside of Telegram.
    """
    repo = UserRepository(session)

    if authorization and authorization.startswith("tma ") and settings.bot_token:
        user_data = _validate_init_data(authorization[4:], settings.bot_token)
        if user_data is None or "id" not in user_data:
            raise HTTPException(status_code=401, detail="Invalid Telegram initData")
        telegram_id = int(user_data["id"])
        user = await repo.get_or_create(
            telegram_id=telegram_id,
            username=user_data.get("username"),
            first_name=user_data.get("first_name", ""),
            avatar_url=user_data.get("photo_url", ""),
            is_admin=telegram_id in settings.admin_id_list,
        )
        await session.commit()
        return user

    if settings.bot_token:
        raise HTTPException(status_code=401, detail="Missing Telegram initData")

    # Development fallback: no bot token configured, use a demo admin user.
    user = await repo.get_or_create(
        telegram_id=1, username="demo", first_name="Demo", is_admin=True
    )
    await session.commit()
    return user


async def get_admin_user(user: User = Depends(get_current_user)) -> User:
    """Require the current user to be an administrator (checked server-side)."""
    if user.role != UserRole.ADMIN and user.telegram_id not in settings.admin_id_list:
        raise HTTPException(status_code=403, detail="Доступ запрещён")
    return user
