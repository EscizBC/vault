"""Единая точка входа: запускает сайт (FastAPI/uvicorn) и Telegram-бота (aiogram)
в одном процессе, в одном event loop.

Использование на хостинге:
    python run.py

Переменные окружения (можно через .env):
    BOT_TOKEN        - токен бота (обязательно для бота; без него запустится только сайт)
    HOST             - хост веб-сервера (по умолчанию 0.0.0.0)
    PORT             - порт веб-сервера (по умолчанию 8000, хостинги обычно задают свой PORT)
"""

import asyncio
import logging
import os
import signal
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

import uvicorn  # noqa: E402
from aiogram import Bot, Dispatcher  # noqa: E402
from aiogram.client.default import DefaultBotProperties  # noqa: E402
from aiogram.enums import ParseMode  # noqa: E402
from aiogram.types import BotCommand  # noqa: E402

from bot.handlers import callback_router, start_router  # noqa: E402
from config import settings  # noqa: E402
from database.db import init_db  # noqa: E402

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
)
logger = logging.getLogger("run")


async def run_web(stop_event: asyncio.Event) -> None:
    """Запуск FastAPI-сервера через uvicorn внутри текущего event loop."""
    host = os.getenv("HOST", "0.0.0.0")
    port = int(os.getenv("PORT", "8000"))

    config = uvicorn.Config(
        "webapp.server:app",
        host=host,
        port=port,
        log_level="info",
        # Управляем сигналами сами, чтобы корректно гасить и бота тоже
        lifespan="on",
    )
    server = uvicorn.Server(config)
    server.install_signal_handlers = lambda: None  # type: ignore[method-assign]

    logger.info("Веб-сервер запускается на http://%s:%s", host, port)
    serve_task = asyncio.create_task(server.serve())

    await stop_event.wait()
    server.should_exit = True
    await serve_task
    logger.info("Веб-сервер остановлен")


async def run_bot(stop_event: asyncio.Event) -> None:
    """Запуск aiogram-бота (long polling)."""
    if not settings.bot_token:
        logger.warning("BOT_TOKEN не задан — бот не запущен, работает только сайт.")
        await stop_event.wait()
        return

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )
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
        logger.exception("Не удалось зарегистрировать команды бота")

    logger.info("Бот запущен (админы: %s)", settings.admin_id_list)

    polling_task = asyncio.create_task(
        dp.start_polling(bot, handle_signals=False)
    )
    stop_waiter = asyncio.create_task(stop_event.wait())

    done, _ = await asyncio.wait(
        {polling_task, stop_waiter},
        return_when=asyncio.FIRST_COMPLETED,
    )

    if stop_waiter in done:
        await dp.stop_polling()
    else:
        # Поллинг упал сам — гасим всё приложение
        stop_event.set()

    try:
        await polling_task
    except Exception:  # noqa: BLE001
        logger.exception("Бот завершился с ошибкой")
    finally:
        await bot.session.close()
        logger.info("Бот остановлен")


async def main() -> None:
    """Инициализация БД и параллельный запуск сайта и бота."""
    await init_db()
    logger.info("База данных готова")

    stop_event = asyncio.Event()

    loop = asyncio.get_running_loop()
    for sig in (signal.SIGINT, signal.SIGTERM):
        try:
            loop.add_signal_handler(sig, stop_event.set)
        except NotImplementedError:
            # Windows: сигналы через add_signal_handler недоступны
            signal.signal(sig, lambda *_: stop_event.set())

    results = await asyncio.gather(
        run_web(stop_event),
        run_bot(stop_event),
        return_exceptions=True,
    )
    for r in results:
        if isinstance(r, Exception):
            logger.error("Компонент завершился с ошибкой: %r", r)


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
