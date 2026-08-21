"""Send Telegram messages from the Web App backend via Bot API."""

import asyncio
import logging

import aiohttp

from config import settings

logger = logging.getLogger(__name__)

_API = "https://api.telegram.org/bot{token}/{method}"


async def _call(method: str, payload: dict) -> bool:
    """Call a Bot API method; returns True on HTTP 200."""
    if not settings.bot_token:
        logger.info("Bot API call skipped (no token): %s", method)
        return False
    url = _API.format(token=settings.bot_token, method=method)
    try:
        async with aiohttp.ClientSession() as http:
            async with http.post(url, json=payload) as resp:
                if resp.status != 200:
                    body = await resp.text()
                    logger.error("Bot API %s failed: HTTP %s %s", method, resp.status, body[:200])
                    return False
                return True
    except aiohttp.ClientError:
        logger.exception("Bot API %s request error", method)
        return False


async def notify_admins(text: str) -> None:
    """Send a plain-text notification to every admin chat."""
    for chat_id in settings.admin_id_list:
        await _call("sendMessage", {"chat_id": chat_id, "text": text})


async def notify_user(chat_id: int, text: str) -> bool:
    """Send a plain-text notification to a single user chat."""
    return await _call("sendMessage", {"chat_id": chat_id, "text": text})


async def send_broadcast(
    telegram_ids: list[int], text: str, photo_url: str | None = None
) -> dict:
    """Send a broadcast (HTML formatting supported) to the given users.

    Returns counters: total, sent, failed.
    """
    sent = 0
    failed = 0
    for chat_id in telegram_ids:
        if photo_url:
            ok = await _call(
                "sendPhoto",
                {"chat_id": chat_id, "photo": photo_url, "caption": text, "parse_mode": "HTML"},
            )
        else:
            ok = await _call(
                "sendMessage",
                {"chat_id": chat_id, "text": text, "parse_mode": "HTML"},
            )
        sent += 1 if ok else 0
        failed += 0 if ok else 1
        await asyncio.sleep(0.05)  # stay under Bot API rate limits
    logger.info("Broadcast finished: %d sent, %d failed", sent, failed)
    return {"total": len(telegram_ids), "sent": sent, "failed": failed}
