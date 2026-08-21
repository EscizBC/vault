"""Payment webhooks: /api/payments (CryptoBot / Crypto Pay)."""

import hashlib
import hmac
import json
import logging

from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from services import PaymentService
from webapp.api.deps import get_db

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/payments", tags=["payments"])


def _verify_signature(body: bytes, signature: str) -> bool:
    """Verify the Crypto Pay webhook signature.

    Per the Crypto Pay docs, the signature is HMAC-SHA256 of the raw body
    with the SHA256 hash of the API token as the key.
    """
    secret = hashlib.sha256(settings.cryptobot_token.encode()).digest()
    expected = hmac.new(secret, body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)


@router.post("/cryptobot/webhook")
async def cryptobot_webhook(
    request: Request,
    session: AsyncSession = Depends(get_db),
    crypto_pay_api_signature: str = Header(default=""),
) -> dict:
    """Handle ``invoice_paid`` updates from Crypto Pay.

    The signature is always verified server-side; the frontend is never
    trusted with payment confirmation.
    """
    if not settings.cryptobot_token:
        raise HTTPException(status_code=503, detail="CryptoBot is not configured")

    body = await request.body()
    if not _verify_signature(body, crypto_pay_api_signature):
        logger.warning("CryptoBot webhook: invalid signature")
        raise HTTPException(status_code=401, detail="Invalid signature")

    update = json.loads(body)
    if update.get("update_type") != "invoice_paid":
        return {"ok": True}

    invoice = update.get("payload", {})
    invoice_id = str(invoice.get("invoice_id", ""))
    # For fiat invoices the credited amount is the fiat amount in USD.
    amount = float(invoice.get("amount", 0))
    if not invoice_id or amount <= 0:
        raise HTTPException(status_code=400, detail="Malformed payload")

    await PaymentService(session).confirm_cryptobot_payment(invoice_id, amount)
    return {"ok": True}
