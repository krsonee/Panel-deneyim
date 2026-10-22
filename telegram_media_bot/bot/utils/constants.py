"""Shared enums and constants: media categories, themes, Telegram media specs."""

from __future__ import annotations

from enum import Enum


class MediaCategory(str, Enum):
    """Top-level content domain the user picked from the main menu."""

    CASINO = "casino"
    SPORTS = "sports"


class CasinoTheme(str, Enum):
    """Casino / slot-game visual themes, modeled after Pragmatic Play key art."""

    SLOT_KEY_ART = "slot_key_art"
    FREESPIN_RAIN = "freespin_rain"
    MASCOT_3D = "mascot_3d"
    JACKPOT_BANNER = "jackpot_banner"


class SportsTheme(str, Enum):
    """Sports-betting visual themes."""

    MATCHDAY_BANNER = "matchday_banner"
    ODDS_BOARD = "odds_board"
    WINNING_TICKET = "winning_ticket"
    LIVE_ACTION = "live_action"


class OutputType(str, Enum):
    """What kind of media asset the user wants generated in the end."""

    IMAGE = "image"
    VIDEO = "video"
    STICKER = "sticker"


class VideoProvider(str, Enum):
    LUMA = "luma"
    RUNWAY = "runway"


# --- Telegram media limits (see https://core.telegram.org/stickers) ---------
TELEGRAM_STICKER_SIZE_PX = 512
TELEGRAM_VIDEO_STICKER_MAX_DURATION_SECONDS = 3.0
TELEGRAM_VIDEO_STICKER_MAX_FILE_SIZE_BYTES = 256 * 1024
TELEGRAM_STATIC_STICKER_MAX_FILE_SIZE_BYTES = 512 * 1024
TELEGRAM_VIDEO_STICKER_FPS = 30

DEFAULT_IMAGE_ASPECT_RATIO = "1:1"
DEFAULT_VIDEO_ASPECT_RATIO = "16:9"

# Quota kinds as stored in the usage table / QuotaService API.
QUOTA_KIND_IMAGE = "image"
QUOTA_KIND_VIDEO = "video"
QUOTA_KIND_STICKER = "sticker"
