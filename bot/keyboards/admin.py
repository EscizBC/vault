"""Inline keyboards for administrators."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from config import settings


def _admin_webapp_button() -> InlineKeyboardButton:
    """Web App button when the URL is HTTPS, plain URL button otherwise.

    Telegram rejects web_app buttons with non-HTTPS URLs (e.g. localhost),
    which would make the whole /admin message fail to send silently.
    """
    url = settings.webapp_url
    if url.lower().startswith("https://"):
        return InlineKeyboardButton(text="Открыть админ-панель", web_app=WebAppInfo(url=url))
    return InlineKeyboardButton(text="Открыть админ-панель", url=url)


def admin_menu_keyboard() -> InlineKeyboardMarkup:
    """Admin panel main menu: everything lives inside the Web App."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_admin_webapp_button()],
            [InlineKeyboardButton(text="Закрыть", callback_data="admin:close")],
        ]
    )


def cancel_keyboard() -> InlineKeyboardMarkup:
    """Cancel button for multi-step admin dialogs."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Отмена", callback_data="admin:cancel")]]
    )
