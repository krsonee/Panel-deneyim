"""Tests for aiosqlite-backed daily quota tracking."""

from __future__ import annotations

import pytest
import pytest_asyncio

from bot.services.database import open_database
from bot.services.quota_service import QuotaService
from bot.utils.exceptions import QuotaExceededError


@pytest_asyncio.fixture
async def quota_service(tmp_path):
    connection = await open_database(tmp_path / "test.db")
    service = QuotaService(connection, limits={"image": 3, "video": 1, "sticker": 2})
    try:
        yield service
    finally:
        await connection.close()


@pytest.mark.asyncio
async def test_initial_status_is_zero_used(quota_service):
    status = await quota_service.get_status(user_id=1, kind="image")
    assert status.used == 0
    assert status.limit == 3
    assert status.remaining == 3
    assert not status.is_exceeded


@pytest.mark.asyncio
async def test_check_and_increment_increases_usage(quota_service):
    status = await quota_service.check_and_increment(user_id=1, kind="image")
    assert status.used == 1
    status = await quota_service.check_and_increment(user_id=1, kind="image")
    assert status.used == 2


@pytest.mark.asyncio
async def test_quota_exceeded_raises_after_limit(quota_service):
    await quota_service.check_and_increment(user_id=1, kind="video")  # uses the only slot
    with pytest.raises(QuotaExceededError) as exc_info:
        await quota_service.check_and_increment(user_id=1, kind="video")
    assert exc_info.value.kind == "video"
    assert exc_info.value.limit == 1
    assert exc_info.value.used == 1


@pytest.mark.asyncio
async def test_quota_is_isolated_per_user(quota_service):
    await quota_service.check_and_increment(user_id=1, kind="sticker")
    await quota_service.check_and_increment(user_id=1, kind="sticker")
    status_user_2 = await quota_service.get_status(user_id=2, kind="sticker")
    assert status_user_2.used == 0


@pytest.mark.asyncio
async def test_quota_is_isolated_per_kind(quota_service):
    await quota_service.check_and_increment(user_id=1, kind="image")
    video_status = await quota_service.get_status(user_id=1, kind="video")
    assert video_status.used == 0


@pytest.mark.asyncio
async def test_get_all_status_returns_every_configured_kind(quota_service):
    statuses = await quota_service.get_all_status(user_id=1)
    kinds = {status.kind for status in statuses}
    assert kinds == {"image", "video", "sticker"}


@pytest.mark.asyncio
async def test_log_generation_records_a_row(quota_service):
    await quota_service.log_generation(
        user_id=1,
        category="casino",
        theme="slot_key_art",
        output_type="image",
        prompt="a test prompt",
        status="ok",
    )
    cursor = await quota_service._connection.execute(  # noqa: SLF001 - test-only introspection
        "SELECT COUNT(*) as cnt FROM generation_log WHERE user_id = ?", (1,)
    )
    row = await cursor.fetchone()
    assert row["cnt"] == 1
