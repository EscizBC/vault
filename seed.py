"""Seed the database with demo digital products. Run once: python seed.py"""

import asyncio
import logging

from database.db import get_session, init_db
from database.repositories import (
    ItemRepository,
    ProductItemRepository,
    SettingRepository,
    UserRepository,
)

ADMIN_TELEGRAM_ID = 6380771602
ADMIN_USERNAME = "saintgeek"

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DEMO_PRODUCTS: list[dict] = [
    {
        "name": "Premium Account",
        "description": "Ready-to-use premium account with full access. Login and password are delivered right after payment.",
        "price": 12.50,
        "image_url": "/static/images/product-account.png",
        "units": [
            "Login: premium_01\nPassword: Xk29!mQz\nEmail: premium01@mail.com",
            "Login: premium_02\nPassword: Vb84#tRw\nEmail: premium02@mail.com",
            "Login: premium_03\nPassword: Qp57$nLd\nEmail: premium03@mail.com",
        ],
    },
    {
        "name": "License Key Pro",
        "description": "Pro version activation license key. One-time key, bound to a single device.",
        "price": 29.99,
        "image_url": "/static/images/product-key.png",
        "units": [
            "Key: PRO-8F2K-91MZ-QW34-TT8L",
            "Key: PRO-2Z7C-44XN-PL90-RB6D",
        ],
    },
    {
        "name": "VPN Subscription 1Y",
        "description": "One-year VPN subscription. Unlimited traffic, 60+ countries, up to 5 devices.",
        "price": 39.00,
        "image_url": "/static/images/product-vpn.png",
        "units": [
            "Login: vpn_user_11\nPassword: Nn31@vXe\nTerm: 12 months",
            "Login: vpn_user_12\nPassword: Ww95&kMa\nTerm: 12 months",
            "Login: vpn_user_13\nPassword: Dd47*hTe\nTerm: 12 months",
            "Login: vpn_user_14\nPassword: Ss62!pQu\nTerm: 12 months",
        ],
    },
    {
        "name": "Gift Card $50",
        "description": "Digital gift card worth $50. The activation code is delivered instantly.",
        "price": 45.00,
        "image_url": "/static/images/product-gift.png",
        "units": [
            "Code: GIFT-50-AK29-BM17-CX40",
            "Code: GIFT-50-DP83-EQ56-FZ92",
        ],
    },
]


async def main() -> None:
    """Create tables and insert demo products when the catalog is empty."""
    await init_db()
    async with get_session() as session:
        users = UserRepository(session)
        await users.get_or_create(
            telegram_id=ADMIN_TELEGRAM_ID,
            username=ADMIN_USERNAME,
            first_name="Admin",
            is_admin=True,
        )
        logger.info("Ensured admin user @%s (%d)", ADMIN_USERNAME, ADMIN_TELEGRAM_ID)

        settings_repo = SettingRepository(session)
        if not await settings_repo.get("wallet_btc"):
            await settings_repo.set("wallet_btc", "bc1qla5m6u88f2v9jl76ej4ddekp8e8dvw9033yffj")
            await settings_repo.set("wallet_eth", "0x7Cc9c6CD8A3D122006d06909814865D30c9F0eD0")
            await settings_repo.set("wallet_usdt_trc20", "TB8r7stxCuoReuSTqyDrHxfCsqBixg7uvM")
            logger.info("Seeded default wallet addresses")

        items = ItemRepository(session)
        units = ProductItemRepository(session)
        existing = await items.list_all()
        if existing:
            logger.info("Catalog already has %d items, skipping seed", len(existing))
            return
        for data in DEMO_PRODUCTS:
            item = await items.create(
                name=data["name"],
                description=data["description"],
                price=data["price"],
                image_url=data["image_url"],
            )
            await units.add_units(item.id, data["units"])
        logger.info("Seeded %d demo products", len(DEMO_PRODUCTS))


if __name__ == "__main__":
    asyncio.run(main())
