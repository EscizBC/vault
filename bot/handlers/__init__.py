"""Bot handlers package."""

from bot.handlers.callback import router as callback_router
from bot.handlers.start import router as start_router

__all__ = ["callback_router", "start_router"]
