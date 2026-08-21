"""Bot entry point: dispatcher setup, handler registration, polling."""

import asyncio
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from aiogram import Bot, Dispatcher  # noqa: E402
from aiogram.client.default import DefaultBotProperties  # noqa: E402
from aiogram.enums import ParseMode  # noqa: E402
from aiogram.types import BotCommand  # noqa: E402

from bot.handlers import callback_router, start_router  # noqa: E402
from config import settings  # noqa: E402
from database.db import init_db  # noqa: E402

logger = logging.getLogger(__name__)


async def main() -> None:
    """Initialize the database and start long polling."""
    if not settings.bot_token:
        logger.error("BOT_TOKEN is not set. Fill in the .env file and restart.")
        sys.exit(1)

    await init_db()

    bot = Bot(token=settings.bot_token, default=DefaultBotProperties(parse_mode=ParseMode.HTML))
    dp = Dispatcher()
    dp.include_router(start_router)
    dp.include_router(callback_router)

    try:
        await bot.set_my_commands(
            [
                BotCommand(command="start", description="Open the shop"),
                BotCommand(command="admin", description="Админ-панель"),
            ]
        )
    except Exception:  # noqa: BLE001
        logger.exception("Failed to register bot commands")

    logger.info("Bot started (admins: %s)", settings.admin_id_list)
    try:
        await dp.start_polling(bot)
    finally:
        await bot.session.close()


if __name__ == "__main__":
    asyncio.run(main())
