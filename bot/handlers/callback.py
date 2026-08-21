"""Inline button callback handlers for users and admins."""

import logging

from aiogram import F, Router
from aiogram.types import CallbackQuery, Message

from bot.keyboards import admin_menu_keyboard, back_keyboard, main_menu_keyboard
from config import settings
from database.db import get_session
from database.repositories import PurchaseRepository, UserRepository

logger = logging.getLogger(__name__)

router = Router(name="callback")


def _is_admin(user_id: int) -> bool:
    """Check whether the user is an administrator."""
    return user_id in settings.admin_id_list


# ------------------------------- User callbacks -------------------------------


@router.callback_query(F.data == "user:menu")
async def cb_user_menu(callback: CallbackQuery) -> None:
    """Return to the main menu."""
    if isinstance(callback.message, Message):
        await callback.message.edit_text("Main menu:", reply_markup=main_menu_keyboard())
    await callback.answer()


@router.callback_query(F.data == "user:balance")
async def cb_user_balance(callback: CallbackQuery) -> None:
    """Show the user's balance."""
    async with get_session() as session:
        user = await UserRepository(session).get_by_telegram_id(callback.from_user.id)
        balance = float(user.balance) if user else 0.0
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            f"Your balance: ${balance:.2f}\n\n"
            "You can top up your balance in the Profile section inside the shop.",
            reply_markup=back_keyboard(),
        )
    await callback.answer()


@router.callback_query(F.data == "user:purchases")
async def cb_user_purchases(callback: CallbackQuery) -> None:
    """Show the user's recent purchases."""
    async with get_session() as session:
        user = await UserRepository(session).get_by_telegram_id(callback.from_user.id)
        purchases = await PurchaseRepository(session).list_for_user(user.id) if user else []
    if not purchases:
        text = "You have no purchases yet."
    else:
        lines = [
            f"{p.item_name} — ${float(p.price):.2f} — {p.created_at:%m/%d/%Y %H:%M}"
            for p in purchases[:10]
        ]
        text = "Recent purchases:\n\n" + "\n".join(lines)
    if isinstance(callback.message, Message):
        await callback.message.edit_text(text, reply_markup=back_keyboard())
    await callback.answer()


@router.callback_query(F.data == "user:help")
async def cb_user_help(callback: CallbackQuery) -> None:
    """Show help information."""
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            "How to use the shop:\n\n"
            "1. Tap \"Open shop\"\n"
            "2. Add products to your cart\n"
            "3. Top up your balance in the profile (CryptoBot or a wallet)\n"
            "4. Confirm the purchase with a swipe in the cart\n"
            "5. Product data will appear in the Purchases section\n\n"
            f"Payment questions: {settings.payment_contact}",
            reply_markup=back_keyboard(),
        )
    await callback.answer()


# ------------------------------- Admin callbacks -------------------------------


@router.callback_query(F.data == "admin:open")
async def cb_admin_open(callback: CallbackQuery) -> None:
    """Point the administrator to the in-app admin panel."""
    if not _is_admin(callback.from_user.id):
        await callback.answer("Нет доступа", show_alert=True)
        return
    if isinstance(callback.message, Message):
        await callback.message.edit_text(
            "Админ-панель находится внутри мини-приложения.\n\n"
            "Откройте магазин — во вкладке «Профиль» появится раздел "
            "«Админ-панель»: товары, единицы товара, балансы, рассылка.",
            reply_markup=admin_menu_keyboard(),
        )
    await callback.answer()


@router.callback_query(F.data == "admin:close")
async def cb_admin_close(callback: CallbackQuery) -> None:
    """Close the admin panel."""
    if isinstance(callback.message, Message):
        await callback.message.delete()
    await callback.answer()
