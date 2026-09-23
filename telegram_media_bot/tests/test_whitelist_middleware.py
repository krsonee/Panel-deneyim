"""Tests for the whitelist access-control middleware."""

from __future__ import annotations

from unittest.mock import AsyncMock, Mock

import pytest
from aiogram.types import CallbackQuery, Message

from bot.middlewares.whitelist import WhitelistMiddleware


@pytest.fixture
def middleware() -> WhitelistMiddleware:
    return WhitelistMiddleware(frozenset({111}))


async def _noop_handler(event, data):
    return "handled"


@pytest.mark.asyncio
async def test_allows_whitelisted_user_through(middleware):
    message = Mock(spec=Message)
    message.answer = AsyncMock()
    data = {"event_from_user": Mock(id=111)}

    result = await middleware(_noop_handler, message, data)

    assert result == "handled"
    message.answer.assert_not_called()


@pytest.mark.asyncio
async def test_blocks_non_whitelisted_user(middleware):
    message = Mock(spec=Message)
    message.answer = AsyncMock()
    data = {"event_from_user": Mock(id=999)}

    result = await middleware(_noop_handler, message, data)

    assert result is None
    message.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_blocks_when_context_has_no_user(middleware):
    message = Mock(spec=Message)
    message.answer = AsyncMock()

    result = await middleware(_noop_handler, message, {})

    assert result is None
    message.answer.assert_awaited_once()


@pytest.mark.asyncio
async def test_blocks_non_whitelisted_callback_query_with_alert(middleware):
    callback = Mock(spec=CallbackQuery)
    callback.answer = AsyncMock()
    data = {"event_from_user": Mock(id=999)}

    result = await middleware(_noop_handler, callback, data)

    assert result is None
    callback.answer.assert_awaited_once_with("Yetkiniz yok.", show_alert=True)


@pytest.mark.asyncio
async def test_empty_whitelist_blocks_everyone():
    middleware = WhitelistMiddleware(frozenset())
    message = Mock(spec=Message)
    message.answer = AsyncMock()
    data = {"event_from_user": Mock(id=111)}

    result = await middleware(_noop_handler, message, data)

    assert result is None
