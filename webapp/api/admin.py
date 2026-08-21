"""Admin API endpoints: /api/admin (server-side role check on every route)."""

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from database.models import User
from database.repositories import UserRepository
from services import AdminService
from webapp.api.deps import get_admin_user, get_db
from webapp.notifier import send_broadcast

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/admin", tags=["admin"])

PRODUCT_IMAGES_DIR = Path(__file__).resolve().parent.parent / "static" / "images" / "products"
MAX_PRODUCT_IMAGE_BYTES = 10 * 1024 * 1024  # 10 MB
PRODUCT_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/heic": ".heic",
    "image/heif": ".heif",
}


@router.post("/upload-image")
async def upload_product_image(
    image: UploadFile = File(...),
    _: User = Depends(get_admin_user),
) -> dict:
    """Upload a product photo (e.g. from a phone) and return its public URL."""
    content_type = (image.content_type or "").lower()
    if content_type not in PRODUCT_IMAGE_TYPES:
        raise HTTPException(status_code=400, detail="Прикрепите изображение (JPG, PNG или WebP)")
    data = await image.read()
    if not data:
        raise HTTPException(status_code=400, detail="Файл пустой")
    if len(data) > MAX_PRODUCT_IMAGE_BYTES:
        raise HTTPException(status_code=400, detail="Файл слишком большой (максимум 10 МБ)")
    PRODUCT_IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    filename = f"{uuid.uuid4().hex}{PRODUCT_IMAGE_TYPES[content_type]}"
    (PRODUCT_IMAGES_DIR / filename).write_bytes(data)
    return {"url": f"/static/images/products/{filename}"}


class RestockRequest(BaseModel):
    """Payload for adding a product or restocking an existing one."""

    item_id: int | None = None
    name: str = Field(default="", max_length=255)
    description: str = Field(default="", max_length=4000)
    price: float | None = Field(default=None, gt=0, le=100_000)
    image_url: str = Field(default="", max_length=512)
    units: list[str] = Field(default_factory=list, max_length=500)


class VisibilityRequest(BaseModel):
    """Payload for hiding/showing a product."""

    item_id: int = Field(gt=0)
    visible: bool


class BalanceAdjustRequest(BaseModel):
    """Payload for a manual balance adjustment."""

    telegram_id: int = Field(gt=0)
    amount: float = Field(gt=0, le=100_000)
    action: str = Field(pattern="^(credit|debit)$")
    comment: str = Field(default="", max_length=512)


class BroadcastRequest(BaseModel):
    """Payload for a broadcast message."""

    text: str = Field(min_length=1, max_length=4000)
    photo_url: str = Field(default="", max_length=512)


class WalletsRequest(BaseModel):
    """Payload for updating deposit wallet addresses."""

    wallet_btc: str = Field(default="", max_length=128)
    wallet_eth: str = Field(default="", max_length=128)
    wallet_usdt_trc20: str = Field(default="", max_length=128)


@router.get("/products")
async def list_products(
    _: User = Depends(get_admin_user), session: AsyncSession = Depends(get_db)
) -> list[dict]:
    """Return every product including hidden ones."""
    return await AdminService(session).list_products()


@router.post("/restock")
async def restock(
    payload: RestockRequest,
    _: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Create a product and/or add digital units to it."""
    try:
        return await AdminService(session).restock(
            name=payload.name,
            description=payload.description,
            price=payload.price,
            image_url=payload.image_url,
            units=payload.units,
            item_id=payload.item_id,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/visibility")
async def set_visibility(
    payload: VisibilityRequest,
    _: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Hide or show a product in the storefront."""
    try:
        return await AdminService(session).set_visibility(payload.item_id, payload.visible)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/user")
async def find_user(
    q: str,
    _: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Find a user by Telegram ID or username."""
    found = await AdminService(session).find_user(q)
    if found is None:
        raise HTTPException(status_code=404, detail="Пользователь не найден")
    return found


@router.post("/balance")
async def adjust_balance(
    payload: BalanceAdjustRequest,
    admin: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Manually credit or debit a user's balance (recorded in history)."""
    try:
        return await AdminService(session).adjust_balance(
            admin, payload.telegram_id, payload.amount, payload.action, payload.comment
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.get("/broadcast/recipients")
async def broadcast_recipients(
    _: User = Depends(get_admin_user), session: AsyncSession = Depends(get_db)
) -> dict:
    """Return the number of users who would receive a broadcast."""
    ids = await UserRepository(session).list_all_telegram_ids()
    return {"count": len(ids)}


@router.post("/broadcast")
async def broadcast(
    payload: BroadcastRequest,
    _: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Send an HTML-formatted broadcast (optionally with a photo) to all users."""
    ids = await UserRepository(session).list_all_telegram_ids()
    return await send_broadcast(ids, payload.text, payload.photo_url or None)


class RequestDecision(BaseModel):
    """Payload for approving or declining a wallet top-up request."""

    transaction_id: int = Field(gt=0)
    approve: bool


@router.get("/requests")
async def list_requests(
    _: User = Depends(get_admin_user), session: AsyncSession = Depends(get_db)
) -> list[dict]:
    """Return pending wallet top-up requests."""
    from services import PaymentService

    return await PaymentService(session).list_wallet_requests()


@router.get("/requests/{tx_id}/screenshot")
async def request_screenshot(
    tx_id: int,
    _: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_db),
):
    """Return the payment screenshot attached to a top-up request (admin only)."""
    from fastapi.responses import FileResponse

    from database.repositories import TransactionRepository
    from webapp.api.user import UPLOADS_DIR

    tx = await TransactionRepository(session).get_by_id(tx_id)
    if tx is None or not tx.screenshot_path:
        raise HTTPException(status_code=404, detail="Скриншот не найден")
    path = (UPLOADS_DIR / tx.screenshot_path).resolve()
    if not str(path).startswith(str(UPLOADS_DIR.resolve())) or not path.is_file():
        raise HTTPException(status_code=404, detail="Скриншот не найден")
    return FileResponse(path)


@router.post("/requests/decision")
async def decide_request(
    payload: RequestDecision,
    _: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Approve (credit the balance) or decline a wallet top-up request."""
    from services import PaymentService
    from webapp.notifier import notify_user

    try:
        result = await PaymentService(session).decide_wallet_request(
            payload.transaction_id, payload.approve
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    if result["telegram_id"]:
        if result["approved"]:
            await notify_user(
                result["telegram_id"],
                f"Your top-up of ${result['amount']:.2f} has been confirmed. "
                f"New balance: ${result['balance']:.2f}",
            )
        else:
            await notify_user(
                result["telegram_id"],
                f"Your top-up request of ${result['amount']:.2f} was declined. "
                "Please contact support if you believe this is a mistake.",
            )
    return {"ok": True}


@router.get("/wallets")
async def get_wallets(
    _: User = Depends(get_admin_user), session: AsyncSession = Depends(get_db)
) -> dict:
    """Return the raw wallet settings for editing."""
    from database.repositories import SettingRepository
    from services.payment_service import WALLET_KEYS

    return await SettingRepository(session).get_many(WALLET_KEYS)


@router.post("/wallets")
async def update_wallets(
    payload: WalletsRequest,
    _: User = Depends(get_admin_user),
    session: AsyncSession = Depends(get_db),
) -> dict:
    """Update deposit wallet addresses (no frontend hardcoding)."""
    await AdminService(session).update_wallets(payload.model_dump())
    return {"ok": True}
