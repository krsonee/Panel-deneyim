"""Whitelist access-control middleware.

Registered as an outer middleware on both the message and callback_query
observers, so it runs before any FSM/handler logic and before quota is
ever touched. Users outside WHITELISTED_USER_IDS get a short Turkish
refusal message and their update never reaches a handler — this is the
primary defense against burning paid API credits on unauthorized use.
"""

from __future__ import annotations

import logging
from typing import Any, Awaitable, Callable

from aiogram import BaseMiddleware
from aiogram.types import CallbackQuery, Message, TelegramObject

logger = logging.getLogger(__name__)

_DENIED_TEXT = (
    "🚫 Bu bot sadece yetkilendirilmiş kullanıcılara açıktır.\n"
    "Erişiminiz yoksa lütfen bot yöneticisiyle iletişime geçin."
)


class WhitelistMiddleware(BaseMiddleware):
    """Blocks any Message/CallbackQuery whose sender is not whitelisted."""

    def __init__(self, whitelisted_user_ids: frozenset[int]):
        super().__init__()
        self._whitelisted_user_ids = whitelisted_user_ids

    async def __call__(
        self,
        handler: Callable[[TelegramObject, dict[str, Any]], Awaitable[Any]],
        event: TelegramObject,
        data: dict[str, Any],
    ) -> Any:
        user = data.get("event_from_user")
        user_id = user.id if user else None

        if user_id is None or user_id not in self._whitelisted_user_ids:
            logger.warning("Yetkisiz erişim denemesi engellendi: user_id=%s", user_id)
            await self._deny(event)
            return None

        return await handler(event, data)

    @staticmethod
    async def _deny(event: TelegramObject) -> None:
        if isinstance(event, Message):
            await event.answer(_DENIED_TEXT)
        elif isinstance(event, CallbackQuery):
            await event.answer("Yetkiniz yok.", show_alert=True)
