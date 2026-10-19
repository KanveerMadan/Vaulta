"""Telegram Bot API calls. Everything goes through `call`, so tests replace it."""

from __future__ import annotations

import logging
from typing import Optional

import httpx

from app.core.config import settings

logger = logging.getLogger(__name__)


class TelegramError(Exception):
    pass


def configured() -> bool:
    return bool(settings.TELEGRAM_BOT_TOKEN)


def call(method: str, payload: dict) -> dict:
    if not configured():
        raise TelegramError("TELEGRAM_BOT_TOKEN isn't set")
    try:
        res = httpx.post(f"https://api.telegram.org/bot{settings.TELEGRAM_BOT_TOKEN}/{method}", json=payload, timeout=10)
        res.raise_for_status()
        return res.json()
    except (httpx.HTTPError, ValueError) as e:
        raise TelegramError(f"{method}: {e.__class__.__name__}") from e


def keyboard(rows: list[list[tuple[str, str]]]) -> dict:
    return {"inline_keyboard": [[{"text": t, "callback_data": d} for t, d in row] for row in rows]}


def send(chat_id: int, text: str, buttons: Optional[list] = None) -> None:
    payload = {"chat_id": chat_id, "text": text[:4000]}
    if buttons:
        payload["reply_markup"] = keyboard(buttons)
    call("sendMessage", payload)


def edit(chat_id: int, message_id: int, text: str, buttons: Optional[list] = None) -> None:
    payload = {"chat_id": chat_id, "message_id": message_id, "text": text[:4000]}
    if buttons:
        payload["reply_markup"] = keyboard(buttons)
    call("editMessageText", payload)


def answer_callback(callback_id: str) -> None:
    call("answerCallbackQuery", {"callback_query_id": callback_id})
