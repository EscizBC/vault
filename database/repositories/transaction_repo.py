"""CRUD repository for balance transactions."""

import logging

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import Transaction, TransactionStatus, TransactionType

logger = logging.getLogger(__name__)


class TransactionRepository:
    """Data access layer for :class:`Transaction`."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session

    async def list_for_user(self, user_id: int, limit: int = 100) -> list[Transaction]:
        """Return transactions for a user, newest first."""
        result = await self._session.execute(
            select(Transaction)
            .where(Transaction.user_id == user_id)
            .order_by(Transaction.id.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def get_by_external_id(self, external_id: str) -> Transaction | None:
        """Return a transaction by its external payment ID (idempotency)."""
        result = await self._session.execute(
            select(Transaction).where(Transaction.external_id == external_id)
        )
        return result.scalar_one_or_none()

    async def get_by_id(self, tx_id: int) -> Transaction | None:
        """Return a transaction by its primary key."""
        return await self._session.get(Transaction, tx_id)

    async def list_pending_wallet_deposits(self, limit: int = 200) -> list[Transaction]:
        """Return pending wallet deposit requests, newest first (cryptobot excluded)."""
        result = await self._session.execute(
            select(Transaction)
            .where(
                Transaction.type == TransactionType.DEPOSIT,
                Transaction.status == TransactionStatus.PENDING,
                Transaction.payment_method != "cryptobot",
            )
            .order_by(Transaction.id.desc())
            .limit(limit)
        )
        return list(result.scalars().all())

    async def create(
        self,
        user_id: int,
        type_: TransactionType,
        amount: float,
        payment_method: str = "",
        status: TransactionStatus = TransactionStatus.COMPLETED,
        comment: str = "",
        external_id: str | None = None,
        screenshot_path: str = "",
    ) -> Transaction:
        """Create a transaction record."""
        tx = Transaction(
            user_id=user_id,
            type=type_,
            amount=amount,
            payment_method=payment_method,
            status=status,
            comment=comment,
            external_id=external_id,
            screenshot_path=screenshot_path,
        )
        self._session.add(tx)
        await self._session.flush()
        logger.info(
            "Transaction id=%s user=%s type=%s amount=%.2f status=%s",
            tx.id, user_id, type_.value, amount, status.value,
        )
        return tx

    async def set_status(self, tx: Transaction, status: TransactionStatus) -> Transaction:
        """Update the status of a transaction."""
        tx.status = status
        await self._session.flush()
        return tx
