"""Wires together Bot, Dispatcher, middlewares, services and handlers.

Kept separate from main.py so the wiring itself (everything except the
actual `asyncio.run` / polling loop) is independently importable and
testable without touching the network.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass

import aiosqlite
from aiogram import Bot, Dispatcher
from aiogram.client.default import DefaultBotProperties
from aiogram.enums import ParseMode
from aiogram.fsm.storage.memory import MemoryStorage

from bot.config import Settings
from bot.handlers import register_handlers
from bot.middlewares.whitelist import WhitelistMiddleware
from bot.services.database import open_database
from bot.services.media_processing_service import MediaProcessingService
from bot.services.openai_image_service import OpenAIImageService
from bot.services.quota_service import QuotaService
from bot.services.video_generation_service import BaseVideoGenerationService, build_video_service

logger = logging.getLogger(__name__)


@dataclass(slots=True)
class BuiltApplication:
    """Every long-lived object created during startup, for main.py to run/close."""

    bot: Bot
    dispatcher: Dispatcher
    db_connection: aiosqlite.Connection
    quota_service: QuotaService
    image_service: OpenAIImageService
    video_service: BaseVideoGenerationService
    media_service: MediaProcessingService


async def build_application(settings: Settings) -> BuiltApplication:
    """Construct every service, the Bot and the Dispatcher, fully wired.

    Does not start polling — that is main.py's job — so this function can
    be reused in tests to verify the wiring without hitting the network.
    """
    db_connection = await open_database(settings.database_path)

    quota_service = QuotaService(
        db_connection,
        limits={
            "image": settings.daily_image_quota,
            "video": settings.daily_video_quota,
            "sticker": settings.daily_sticker_quota,
        },
    )
    image_service = OpenAIImageService(
        api_key=settings.openai_api_key,
        model=settings.openai_image_model,
        size=settings.openai_image_size,
        request_timeout_seconds=settings.request_timeout_seconds,
    )
    video_service = build_video_service(
        provider=settings.video_provider,
        luma_api_key=settings.luma_api_key,
        luma_base_url=settings.luma_api_base_url,
        runway_api_key=settings.runway_api_key,
        runway_base_url=settings.runway_api_base_url,
        request_timeout_seconds=settings.request_timeout_seconds,
    )
    media_service = MediaProcessingService(
        ffmpeg_binary=settings.ffmpeg_binary,
        tmp_dir=settings.media_tmp_dir,
    )

    bot = Bot(
        token=settings.bot_token,
        default=DefaultBotProperties(parse_mode=ParseMode.HTML),
    )

    dispatcher = Dispatcher(
        storage=MemoryStorage(),
        settings=settings,
        quota_service=quota_service,
        image_service=image_service,
        video_service=video_service,
        media_service=media_service,
    )

    whitelist_middleware = WhitelistMiddleware(settings.whitelisted_user_ids)
    dispatcher.message.outer_middleware(whitelist_middleware)
    dispatcher.callback_query.outer_middleware(whitelist_middleware)

    register_handlers(dispatcher)

    logger.info(
        "Uygulama hazır: %s beyaz listede kullanıcı, video sağlayıcı=%s (%s), OpenAI %s.",
        len(settings.whitelisted_user_ids),
        settings.video_provider,
        "yapılandırıldı" if settings.is_video_provider_configured else "TODO: API key eksik",
        "yapılandırıldı" if settings.is_openai_configured else "TODO: API key eksik",
    )

    return BuiltApplication(
        bot=bot,
        dispatcher=dispatcher,
        db_connection=db_connection,
        quota_service=quota_service,
        image_service=image_service,
        video_service=video_service,
        media_service=media_service,
    )
