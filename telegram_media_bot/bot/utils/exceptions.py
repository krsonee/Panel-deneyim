"""Custom exception hierarchy shared across services and handlers."""

from __future__ import annotations


class BotError(Exception):
    """Base class for all bot-specific errors."""


class QuotaExceededError(BotError):
    """Raised when a user has exhausted their daily quota for a media kind."""

    def __init__(self, kind: str, limit: int, used: int):
        self.kind = kind
        self.limit = limit
        self.used = used
        super().__init__(f"Daily quota exceeded for kind={kind!r} (used={used}, limit={limit})")


class MediaGenerationError(BotError):
    """Base class for all media-generation related errors."""


class ImageGenerationError(MediaGenerationError):
    """Raised when the image generation provider (DALL-E 3) fails."""


class VideoGenerationError(MediaGenerationError):
    """Raised when the video generation provider (Luma/Runway) fails."""


class MediaProcessingError(MediaGenerationError):
    """Raised on local ffmpeg/rembg processing failures."""


class ProviderNotConfiguredError(MediaGenerationError):
    """Raised when a provider is invoked without its required API key.

    This is the expected error in this scaffold until real API keys are
    supplied via .env — handlers catch it and show the user a friendly,
    Turkish "servis henüz yapılandırılmadı" message instead of crashing.
    """

    def __init__(self, provider_name: str, env_var: str):
        self.provider_name = provider_name
        self.env_var = env_var
        super().__init__(f"{provider_name} not configured; missing {env_var} in .env")
