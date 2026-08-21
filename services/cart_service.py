"""Business logic for the shopping cart and checkout with digital delivery."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from database.models import ProductItem, TransactionType, User
from database.repositories import (
    CartRepository,
    ItemRepository,
    ProductItemRepository,
    PurchaseRepository,
    TransactionRepository,
    UserRepository,
)

logger = logging.getLogger(__name__)


class CartService:
    """Cart-related use cases: view, mutate, checkout with unit reservation."""

    def __init__(self, session: AsyncSession) -> None:
        self._session = session
        self._carts = CartRepository(session)
        self._items = ItemRepository(session)
        self._units = ProductItemRepository(session)
        self._users = UserRepository(session)
        self._purchases = PurchaseRepository(session)
        self._transactions = TransactionRepository(session)

    async def get_cart(self, user: User) -> dict:
        """Return the serialized cart with a server-computed total."""
        rows = await self._carts.list_for_user(user.id)
        items = [
            {
                "item_id": row.item_id,
                "name": row.item.name,
                "price": float(row.item.price),
                "image_url": row.item.image_url,
                "quantity": row.quantity,
                "subtotal": round(float(row.item.price) * row.quantity, 2),
            }
            for row in rows
            if row.item is not None and row.item.is_active
        ]
        total = round(sum(entry["subtotal"] for entry in items), 2)
        return {"items": items, "total": total, "count": sum(e["quantity"] for e in items)}

    async def add_to_cart(self, user: User, item_id: int, quantity: int = 1) -> dict:
        """Validate the product and add it to the cart.

        Raises:
            ValueError: If the product does not exist, is hidden, is out of
                stock, or the quantity is invalid.
        """
        if quantity < 1 or quantity > 99:
            raise ValueError("Invalid quantity")
        item = await self._items.get(item_id)
        if item is None or not item.is_active:
            raise ValueError("Product not found")
        available = await self._units.count_available(item_id)
        if available < 1:
            raise ValueError("Product is out of stock")
        existing = await self._carts.get(user.id, item_id)
        in_cart = existing.quantity if existing else 0
        if in_cart + quantity > available:
            raise ValueError(f"Only {available} pcs available")
        await self._carts.add(user.id, item_id, quantity)
        return await self.get_cart(user)

    async def set_quantity(self, user: User, item_id: int, quantity: int) -> dict:
        """Set an exact quantity for a cart row (0 removes it).

        Raises:
            ValueError: If the quantity is invalid or exceeds availability.
        """
        if quantity < 0 or quantity > 99:
            raise ValueError("Invalid quantity")
        if quantity > 0:
            available = await self._units.count_available(item_id)
            if quantity > available:
                raise ValueError(f"Only {available} pcs available")
        await self._carts.set_quantity(user.id, item_id, quantity)
        return await self.get_cart(user)

    async def remove_from_cart(self, user: User, item_id: int) -> dict:
        """Remove an item from the cart."""
        await self._carts.remove(user.id, item_id)
        return await self.get_cart(user)

    async def checkout(self, user: User) -> dict:
        """Charge the balance and deliver one digital unit per cart quantity.

        Flow per the spec: check balance -> reserve units (locking) ->
        deduct balance -> mark units sold -> create purchases -> record the
        transaction -> clear the cart. Everything runs inside one DB
        transaction, so any failure rolls the whole operation back.

        Raises:
            ValueError: If the cart is empty, the balance is insufficient,
                or a unit is no longer available.
        """
        cart = await self.get_cart(user)
        if not cart["items"]:
            raise ValueError("Your cart is empty")
        total = cart["total"]
        if float(user.balance) < total:
            raise ValueError("Insufficient balance")

        # Reserve every unit first so a concurrent checkout cannot take them.
        reserved: list[tuple[dict, ProductItem]] = []
        for entry in cart["items"]:
            for _ in range(entry["quantity"]):
                unit = await self._units.reserve_one(entry["item_id"])
                if unit is None:
                    # Roll back reservations made so far and abort.
                    for _, taken in reserved:
                        await self._units.release(taken)
                    raise ValueError(f"\"{entry['name']}\" is sold out. Please refresh your cart.")
                reserved.append((entry, unit))

        await self._users.deduct_balance(user, total)

        purchases = []
        for entry, unit in reserved:
            await self._units.mark_sold(unit, user.id)
            purchase = await self._purchases.create(
                user_id=user.id,
                item_id=entry["item_id"],
                product_item_id=unit.id,
                item_name=entry["name"],
                price=entry["price"],
            )
            purchases.append(purchase.id)

        await self._transactions.create(
            user_id=user.id,
            type_=TransactionType.PURCHASE,
            amount=-total,
            payment_method="balance",
            comment=f"Purchase of {len(reserved)} item(s)",
        )
        await self._carts.clear(user.id)
        logger.info(
            "Checkout complete user=%s total=%.2f purchases=%s",
            user.telegram_id, total, purchases,
        )
        return {
            "purchase_ids": purchases,
            "total": total,
            "balance": float(user.balance),
        }
