"""End-to-end wiring smoke test: builds the whole app without any network calls.

Bot() construction and Dispatcher/router registration never touch the
network in aiogram 3 (only start_polling()/get_me() do), so this test
proves main.py's dependency graph is correctly assembled without needing
a real bot token or any provider API keys.
"""

from __future__ import annotations

import pytest

from bot.config import load_settings
from bot.loader import build_application


@pytest.mark.asyncio
async def test_build_application_wires_bot_dispatcher_and_services(tmp_path, monkeypatch):
    for key in ("BOT_TOKEN", "WHITELISTED_USER_IDS", "VIDEO_PROVIDER"):
        monkeypatch.delenv(key, raising=False)
    env_file = tmp_path / ".env"
    env_file.write_text(
        "BOT_TOKEN=123456:test-token\n"
        "WHITELISTED_USER_IDS=111\n"
        f"DATABASE_PATH={tmp_path / 'bot.db'}\n"
        f"MEDIA_TMP_DIR={tmp_path / 'tmp'}\n"
    )
    settings = load_settings(env_file)

    app = await build_application(settings)
    try:
        assert app.bot.token == "123456:test-token"

        workflow_data = app.dispatcher.workflow_data
        assert workflow_data["quota_service"] is app.quota_service
        assert workflow_data["image_service"] is app.image_service
        assert workflow_data["video_service"] is app.video_service
        assert workflow_data["media_service"] is app.media_service
        assert workflow_data["settings"] is settings

        # Whitelist middleware is registered as an outer middleware on both
        # observers that carry a `from_user` (message + callback_query).
        assert len(app.dispatcher.message.outer_middleware) == 1
        assert len(app.dispatcher.callback_query.outer_middleware) == 1

        # All handler routers were included (start, menu, casino, sports,
        # generation, quota, fallback).
        sub_router_names = {router.name for router in app.dispatcher.sub_routers}
        assert {"start", "menu", "casino", "sports", "generation", "quota", "fallback"} <= sub_router_names
    finally:
        await app.db_connection.close()
        await app.bot.session.close()
