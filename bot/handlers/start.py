"""/start and /admin command handlers."""

import logging

from aiogram import Router
from aiogram.filters import Command, CommandStart
from aiogram.types import Message

from bot.keyboards import admin_menu_keyboard, main_menu_keyboard
from config import settings
from database.db import get_session
from database.repositories import UserRepository

logger = logging.getLogger(__name__)

router = Router(name="start")


@router.message(CommandStart())
async def cmd_start(message: Message) -> None:
    """Greet the user, register them in the DB and show the Web App button."""
    if message.from_user is None:
        return
    async with get_session() as session:
        repo = UserRepository(session)
        await repo.get_or_create(
            telegram_id=message.from_user.id,
            username=message.from_user.username,
            first_name=message.from_user.first_name or "",
            is_admin=message.from_user.id in settings.admin_id_list,
        )
    logger.info("User %s started the bot", message.from_user.id)
    greeting = (
        f"Hi, {message.from_user.first_name}!\n\n"
        "Welcome to our shop. Tap the button below "
        "to open the catalog, cart and profile."
    )
    try:
        await message.answer(greeting, reply_markup=main_menu_keyboard())
    except Exception:
        logger.exception(
            "Failed to send /start reply with keyboard (check WEBAPP_URL, "
            "Telegram requires HTTPS for Web App buttons). Sending plain text."
        )
        await message.answer(
            greeting + "\n\nThe shop is temporarily unavailable: HTTPS WEBAPP_URL is not configured."
        )


@router.message(Command("admin"))
async def cmd_admin(message: Message) -> None:
    """Show the admin panel to authorized administrators."""
    if message.from_user is None:
        return
    if message.from_user.id not in settings.admin_id_list:
        await message.answer("У вас нет доступа к админ-панели.")
        logger.warning("Unauthorized /admin attempt by %s", message.from_user.id)
        return
    try:
        await message.answer(
            "Админ-панель:\n\n"
            "Всё управление находится внутри мини-приложения — "
            "вкладка «Профиль» → «Админ-панель».",
            reply_markup=admin_menu_keyboard(),
        )
    except Exception:
        logger.exception("Failed to send /admin reply with keyboard (check WEBAPP_URL)")
        await message.answer(
            "Админ-панель находится внутри мини-приложения: "
            "откройте магазин и перейдите в «Профиль» → «Админ-панель»."
        )
