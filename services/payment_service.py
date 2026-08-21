"""Business logic for balance top-ups: CryptoBot invoices and wallet deposits."""

import logging

import aiohttp
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database.models import TransactionStatus, TransactionType, User
from database.repositories import (
    SettingRepository,
    TransactionRepository,
    UserRepository,
)

logger = logging.getLogger(__name__)

MIN_TOPUP = 1.0
MAX_TOPUP = 10_000.0

WALLET_KEYS = ["wallet_btc", "wallet_eth", "wallet_usdt_trc20"]
WALLET_LABELS = {
    "wallet_btc": "BTC",
    "wallet_eth": "ETH",
    "wallet_usdt_trc20": "USDT TRC20",
}


class PaymentService:
    """Top-up use cases."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._users = UserRepository(session)
        self._transactions = TransactionRepository(session)
        self._settings = SettingRepository(session)

    # ------------------------------ CryptoBot ------------------------------

    async def create_cryptobot_invoice(self, user: User, amount: float) -> dict:
        """Create a Crypto Pay invoice and a pending transaction.

        Raises:
            ValueError: If the amount is out of range or CryptoBot is not
                configured / rejects the request.
        """
        amount = round(float(amount), 2)
        if amount < MIN_TOPUP or amount > MAX_TOPUP:
            raise ValueError(f"Amount must be between ${MIN_TOPUP:.0f} and ${MAX_TOPUP:.0f}")
        if not settings.cryptobot_token:
            raise ValueError("CryptoBot is not configured. Please contact the administrator.")

        payload = {
            "currency_type": "fiat",
            "fiat": "USD",
            "amount": f"{amount:.2f}",
            "accepted_assets": "USDT,TON,BTC,ETH",
            "description": f"Balance top-up of ${amount:.2f}",
            "payload": str(user.telegram_id),
        }
        async with aiohttp.ClientSession() as http:
            async with http.post(
                f"{settings.cryptobot_api_url}/createInvoice",
                json=payload,
                headers={"Crypto-Pay-API-Token": settings.cryptobot_token},
            ) as resp:
                data = await resp.json()
        if not data.get("ok"):
            logger.error("CryptoBot createInvoice failed: %s", data)
            raise ValueError("Failed to create an invoice. Please try again later.")

        invoice = data["result"]
        await self._transactions.create(
            user_id=user.id,
            type_=TransactionType.DEPOSIT,
            amount=amount,
            payment_method="cryptobot",
            status=TransactionStatus.PENDING,
            comment=f"CryptoBot invoice #{invoice['invoice_id']}",
            external_id=str(invoice["invoice_id"]),
        )
        return {
            "invoice_id": invoice["invoice_id"],
            "pay_url": invoice.get("mini_app_invoice_url") or invoice["pay_url"],
        }

    async def confirm_cryptobot_payment(self, invoice_id: str, amount: float) -> None:
        """Credit the balance for a paid invoice (webhook / bot polling).

        Idempotent: an already-completed transaction is skipped.
        """
        tx = await self._transactions.get_by_external_id(str(invoice_id))
        if tx is None or tx.status == TransactionStatus.COMPLETED:
            return
        user = await self._users.get_by_id(tx.user_id)
        if user is None:
            return
        await self._users.add_balance(user, float(amount))
        await self._transactions.set_status(tx, TransactionStatus.COMPLETED)
        logger.info("CryptoBot invoice %s confirmed: +$%.2f", invoice_id, amount)

    # ------------------------------ Wallets ------------------------------

    async def get_wallets(self) -> list[dict]:
        """Return deposit wallet addresses stored in settings (not hardcoded)."""
        values = await self._settings.get_many(WALLET_KEYS)
        return [
            {"key": key, "label": WALLET_LABELS[key], "address": values[key]}
            for key in WALLET_KEYS
            if values[key]
        ]

    async def create_wallet_request(
        self, user: User, amount: float, wallet_key: str, screenshot_path: str = ""
    ) -> dict:
        """Register a pending wallet deposit awaiting admin confirmation.

        Raises:
            ValueError: If the amount or wallet is invalid.
        """
        amount = round(float(amount), 2)
        if amount < MIN_TOPUP or amount > MAX_TOPUP:
            raise ValueError(f"Amount must be between ${MIN_TOPUP:.0f} and ${MAX_TOPUP:.0f}")
        if wallet_key not in WALLET_KEYS:
            raise ValueError("Unknown top-up method")
        tx = await self._transactions.create(
            user_id=user.id,
            type_=TransactionType.DEPOSIT,
            amount=amount,
            payment_method=WALLET_LABELS[wallet_key],
            status=TransactionStatus.PENDING,
            comment="Awaiting payment confirmation",
            screenshot_path=screenshot_path,
        )
        return {"transaction_id": tx.id}

    async def list_wallet_requests(self) -> list[dict]:
        """Return pending wallet deposit requests with user info (for admins)."""
        txs = await self._transactions.list_pending_wallet_deposits()
        out = []
        for tx in txs:
            user = await self._users.get_by_id(tx.user_id)
            out.append(
                {
                    "id": tx.id,
                    "amount": float(tx.amount),
                    "payment_method": tx.payment_method,
                    "created_at": tx.created_at.isoformat() if tx.created_at else None,
                    "has_screenshot": bool(tx.screenshot_path),
                    "user": {
                        "telegram_id": user.telegram_id if user else None,
                        "username": user.username if user else None,
                        "first_name": user.first_name if user else "",
                    },
                }
            )
        return out

    async def decide_wallet_request(self, tx_id: int, approve: bool) -> dict:
        """Approve (credit balance) or decline a pending wallet deposit.

        Returns a dict with the affected user's telegram_id for notification.

        Raises:
            ValueError: If the request does not exist or is not pending.
        """
        tx = await self._transactions.get_by_id(tx_id)
        if tx is None or tx.type != TransactionType.DEPOSIT:
            raise ValueError("Заявка не найдена")
        if tx.status != TransactionStatus.PENDING:
            raise ValueError("Заявка уже обработана")
        user = await self._users.get_by_id(tx.user_id)
        if user is None:
            raise ValueError("Пользователь не найден")
        if approve:
            await self._users.add_balance(user, float(tx.amount))
            await self._transactions.set_status(tx, TransactionStatus.COMPLETED)
            tx.comment = "Confirmed by admin"
        else:
            await self._transactions.set_status(tx, TransactionStatus.FAILED)
            tx.comment = "Declined by admin"
        return {
            "telegram_id": user.telegram_id,
            "amount": float(tx.amount),
            "approved": approve,
            "balance": float(user.balance),
        }

    # ------------------------------ History ------------------------------

    async def list_transactions(self, user: User) -> list[dict]:
        """Return the user's transaction history."""
        txs = await self._transactions.list_for_user(user.id)
        method_labels = {"cryptobot": "CryptoBot", "balance": "Balance", "admin": "Admin"}
        return [
            {
                "id": tx.id,
                "type": tx.type.value,
                "payment_method": method_labels.get(tx.payment_method, tx.payment_method or "—"),
                "amount": float(tx.amount),
                "status": tx.status.value,
                "comment": tx.comment,
                "created_at": tx.created_at.isoformat() if tx.created_at else None,
            }
            for tx in txs
        ]
