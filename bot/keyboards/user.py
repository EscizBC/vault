"""Inline keyboards for regular users."""

from aiogram.types import InlineKeyboardButton, InlineKeyboardMarkup, WebAppInfo

from config import settings


def _shop_button() -> InlineKeyboardButton:
    """Web App button when the URL is HTTPS, plain URL button otherwise.

    Telegram rejects web_app buttons with non-HTTPS URLs (e.g. localhost),
    which would make the whole message fail to send.
    """
    url = settings.webapp_url
    if url.lower().startswith("https://"):
        return InlineKeyboardButton(text="Open shop", web_app=WebAppInfo(url=url))
    return InlineKeyboardButton(text="Open shop", url=url)


def main_menu_keyboard() -> InlineKeyboardMarkup:
    """Main menu with a Web App button and quick actions."""
    return InlineKeyboardMarkup(
        inline_keyboard=[
            [_shop_button()],
            [
                InlineKeyboardButton(text="My balance", callback_data="user:balance"),
                InlineKeyboardButton(text="My purchases", callback_data="user:purchases"),
            ],
            [InlineKeyboardButton(text="Help", callback_data="user:help")],
        ]
    )


def back_keyboard() -> InlineKeyboardMarkup:
    """A single Back button."""
    return InlineKeyboardMarkup(
        inline_keyboard=[[InlineKeyboardButton(text="Back", callback_data="user:menu")]]
    )
