"""FastAPI application: CORS, routers, static SPA."""

import logging
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from database.db import init_db
from webapp.api import admin, cart, items, payments, purchases, user

logger = logging.getLogger(__name__)

STATIC_DIR = Path(__file__).parent / "static"


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Initialize the database on startup."""
    await init_db()
    logger.info("Web App server started")
    yield


app = FastAPI(title="Telegram Mini App Shop", lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=False,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(items.router)
app.include_router(cart.router)
app.include_router(purchases.router)
app.include_router(user.router)
app.include_router(admin.router)
app.include_router(payments.router)

app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")


@app.get("/", include_in_schema=False)
async def index() -> FileResponse:
    """Serve the SPA entry point."""
    return FileResponse(STATIC_DIR / "index.html")
