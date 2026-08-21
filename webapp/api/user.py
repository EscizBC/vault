"""API endpoints for the user profile and top-ups: /api/user."""

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from config import settings
from database.models import User, UserRole
from services import PaymentService
from webapp.api.deps import get_current_user, get_db
from webapp.notifier import notify_admins

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/user", tags=["user"])

UPLOADS_DIR = Path(__file__).resolve().parent.parent.parent / "uploads"
MAX_SCREENSHOT_BYTES = 10 * 1024 * 1024  # 10 MB
ALLOWED_IMAGE_TYPES = {"image/jpeg", "image/png", "image/webp", "image/heic", "image/heif"}


class CryptoBotTopUpRequest(BaseModel):
    """Payload for a CryptoBot top-up."""

    amount: float = Field(gt=0, le=10_000)





@router.get("")
async def get_profile(user: User = Depends(get_current_user)) -> dict:
    """Return the current user's profile."""
    return {
        "telegram_id": user.telegram_id,
        "username": user.username,
        "first_name": user.first_name,
        "avatar_url": user.avatar_url,
        "balance": float(user.balance),
        "is_admin": user.role == UserRole.ADMIN
        or user.telegram_id in settings.admin_id_list,
    }


@router.get("/transactions")
async def list_transactions(
    user: User = Depends(get_current_user), session: AsyncSession = Depends(get_db)
) -> list[dict]:
    """Return the current user's transaction history."""
    return await PaymentService(session).list_transactions(user)


@router.get("/wallets")
async def get_wallets(
    _: User = Depends(get_current_user), session: AsyncSession = Depends(get_db)
) -> list[dict]:
    """Return deposit wallet addresses (stored in settings, not hardcoded)."""
    return await PaymentService(session).get_wallets()


@router.post("/topup/cryptobot")
async def topup_cryptobot(
    payload: CryptoBotTopUpRequest,
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Create a CryptoBot invoice and return the payment URL."""
    try:
        return await PaymentService(session).create_cryptobot_invoice(user, payload.amount)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/topup/wallet")
async def topup_wallet(
    amount: float = Form(gt=0, le=10_000),
    wallet_key: str = Form(min_length=1, max_length=64),
    screenshot: UploadFile = File(...),
    user: User = Depends(get_current_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Register a pending wallet deposit with a payment screenshot and notify the admins."""
    content_type = (screenshot.content_type or "").lower()
    if content_type not in ALLOWED_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Attach an image (JPG, PNG or WebP)")
    data = await screenshot.read()
    if not data:
        raise HTTPException(status_code=400, detail="The screenshot file is empty")
    if len(data) > MAX_SCREENSHOT_BYTES:
        raise HTTPException(status_code=400, detail="Screenshot is too large (max 10 MB)")

    ext = {"image/jpeg": ".jpg", "image/png": ".png", "image/webp": ".webp",
           "image/heic": ".heic", "image/heif": ".heif"}[content_type]
    UPLOADS_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{ext}"
    (UPLOADS_DIR / filename).write_bytes(data)

    try:
        result = await PaymentService(session).create_wallet_request(
            user, amount, wallet_key, screenshot_path=filename
        )
    except ValueError as exc:
        (UPLOADS_DIR / filename).unlink(missing_ok=True)
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    await notify_admins(
        f"Заявка на пополнение через кошелёк\n"
        f"Пользователь: @{user.username or user.telegram_id} (ID {user.telegram_id})\n"
        f"Сумма: ${amount:.2f}\n"
        f"Способ: {wallet_key}\n"
        f"Транзакция: #{result['transaction_id']}\n"
        f"Скриншот приложен — проверьте вкладку «Заявки» в админ-панели"
    )
    return result
