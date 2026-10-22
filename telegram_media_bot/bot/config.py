"""Application configuration, loaded from environment variables / .env file.

This module is intentionally dependency-light (stdlib + python-dotenv only) so
that configuration can be loaded and validated before any heavier packages
(aiogram, openai, rembg, ...) are imported.
"""

from __future__ import annotations

import logging
import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv

logger = logging.getLogger(__name__)

# Repo root of this standalone bot project (telegram_media_bot/).
BASE_DIR = Path(__file__).resolve().parent.parent


class ConfigError(RuntimeError):
    """Raised when required configuration is missing or invalid."""


def _parse_id_list(raw: str | None) -> frozenset[int]:
    """Parse a comma-separated list of Telegram user ids into a set of ints."""
    if not raw:
        return frozenset()
    ids: set[int] = set()
    for chunk in raw.split(","):
        chunk = chunk.strip()
        if not chunk:
            continue
        try:
            ids.add(int(chunk))
        except ValueError:
            logger.warning("Ignoring invalid user_id value in whitelist: %r", chunk)
    return frozenset(ids)


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError:
        logger.warning("Invalid integer for %s=%r, falling back to default %s", name, raw, default)
        return default


@dataclass(frozen=True, slots=True)
class Settings:
    """Fully validated runtime configuration for the bot."""

    bot_token: str
    whitelisted_user_ids: frozenset[int]

    daily_image_quota: int
    daily_video_quota: int
    daily_sticker_quota: int

    openai_api_key: str | None
    openai_image_model: str
    openai_image_size: str

    video_provider: str
    luma_api_key: str | None
    luma_api_base_url: str
    runway_api_key: str | None
    runway_api_base_url: str

    database_path: Path
    media_tmp_dir: Path
    ffmpeg_binary: str

    log_level: str
    request_timeout_seconds: int

    @property
    def is_whitelist_configured(self) -> bool:
        return bool(self.whitelisted_user_ids)

    @property
    def is_openai_configured(self) -> bool:
        return bool(self.openai_api_key)

    @property
    def is_video_provider_configured(self) -> bool:
        if self.video_provider == "luma":
            return bool(self.luma_api_key)
        if self.video_provider == "runway":
            return bool(self.runway_api_key)
        return False


_VALID_VIDEO_PROVIDERS = {"luma", "runway"}


def load_settings(env_file: str | Path | None = None) -> Settings:
    """Load and validate settings from the process environment / .env file.

    Args:
        env_file: Optional explicit path to a .env file. When omitted,
            python-dotenv searches upward from the current working
            directory for a ``.env`` file, which matches running the bot
            from the ``telegram_media_bot/`` project root.
    """
    load_dotenv(dotenv_path=env_file, override=False)

    bot_token = os.getenv("BOT_TOKEN", "").strip()
    if not bot_token:
        raise ConfigError(
            "BOT_TOKEN tanımlı değil. .env dosyasını .env.example'dan kopyalayıp "
            "BotFather'dan aldığınız token değerini girin."
        )

    database_path = Path(os.getenv("DATABASE_PATH", str(BASE_DIR / "data" / "bot.db"))).expanduser()
    media_tmp_dir = Path(os.getenv("MEDIA_TMP_DIR", str(BASE_DIR / "data" / "tmp"))).expanduser()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    media_tmp_dir.mkdir(parents=True, exist_ok=True)

    video_provider = os.getenv("VIDEO_PROVIDER", "luma").strip().lower()
    if video_provider not in _VALID_VIDEO_PROVIDERS:
        raise ConfigError(
            f"VIDEO_PROVIDER geçersiz: {video_provider!r}. "
            f"Geçerli değerler: {', '.join(sorted(_VALID_VIDEO_PROVIDERS))}."
        )

    settings = Settings(
        bot_token=bot_token,
        whitelisted_user_ids=_parse_id_list(os.getenv("WHITELISTED_USER_IDS")),
        daily_image_quota=_env_int("DAILY_IMAGE_QUOTA", 20),
        daily_video_quota=_env_int("DAILY_VIDEO_QUOTA", 5),
        daily_sticker_quota=_env_int("DAILY_STICKER_QUOTA", 15),
        openai_api_key=os.getenv("OPENAI_API_KEY") or None,
        openai_image_model=os.getenv("OPENAI_IMAGE_MODEL", "dall-e-3"),
        openai_image_size=os.getenv("OPENAI_IMAGE_SIZE", "1024x1024"),
        video_provider=video_provider,
        luma_api_key=os.getenv("LUMA_API_KEY") or None,
        luma_api_base_url=os.getenv(
            "LUMA_API_BASE_URL", "https://api.lumalabs.ai/dream-machine/v1"
        ),
        runway_api_key=os.getenv("RUNWAY_API_KEY") or None,
        runway_api_base_url=os.getenv("RUNWAY_API_BASE_URL", "https://api.runwayml.com/v1"),
        database_path=database_path,
        media_tmp_dir=media_tmp_dir,
        ffmpeg_binary=os.getenv("FFMPEG_BINARY", "ffmpeg"),
        log_level=os.getenv("LOG_LEVEL", "INFO").upper(),
        request_timeout_seconds=_env_int("REQUEST_TIMEOUT_SECONDS", 60),
    )

    if not settings.is_whitelist_configured:
        logger.warning(
            "WHITELISTED_USER_IDS boş bırakıldı; hiçbir kullanıcı botu kullanamayacak. "
            "Kendi Telegram user_id'nizi .env dosyasına eklemeyi unutmayın."
        )

    return settings
