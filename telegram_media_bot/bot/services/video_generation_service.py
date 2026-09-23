"""Video/animation generation via Luma Dream Machine or Runway Gen-3 Alpha.

Both providers follow the same async job pattern: submit a generation
request, poll a status endpoint until it finishes, then download the
resulting video file. That shared shape is captured in
`BaseVideoGenerationService`; each provider only implements the three
HTTP calls (submit / poll / extract download url).

TODO(production): the exact request/response JSON shapes below follow the
providers' public docs as of this writing (Luma Dream Machine API,
Runway Gen-3 Alpha "image_to_video" API). Verify field names against the
current API reference before going live — these vendors have iterated
their APIs quickly, and endpoints/fields can change between releases.
"""

from __future__ import annotations

import abc
import asyncio
import logging

import aiohttp

from bot.utils.exceptions import ProviderNotConfiguredError, VideoGenerationError

logger = logging.getLogger(__name__)

_POLL_INTERVAL_SECONDS = 5.0
_MAX_POLL_ATTEMPTS = 60  # ~5 minutes at 5s interval


class BaseVideoGenerationService(abc.ABC):
    """Common submit -> poll -> download flow for image-to-video providers."""

    provider_name: str = "unknown"

    def __init__(self, api_key: str | None, base_url: str, request_timeout_seconds: int = 60):
        self._api_key = api_key
        self._base_url = base_url.rstrip("/")
        self._timeout = request_timeout_seconds

    @property
    def is_configured(self) -> bool:
        return bool(self._api_key)

    def _require_configured(self, env_var: str) -> None:
        if not self._api_key:
            raise ProviderNotConfiguredError(self.provider_name, env_var)

    async def generate_video(
        self,
        prompt: str,
        source_image_bytes: bytes | None = None,
        negative_prompt: str | None = None,
        aspect_ratio: str = "16:9",
    ) -> bytes:
        """Submit a generation job, poll until done, and return raw video bytes."""
        async with aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self._timeout)
        ) as session:
            job_id = await self._submit(session, prompt, source_image_bytes, negative_prompt, aspect_ratio)
            logger.info("%s işi gönderildi: job_id=%s", self.provider_name, job_id)

            for attempt in range(1, _MAX_POLL_ATTEMPTS + 1):
                status, video_url = await self._poll(session, job_id)
                logger.debug("%s durum kontrolü (%s/%s): %s", self.provider_name, attempt, _MAX_POLL_ATTEMPTS, status)
                if status == "completed" and video_url:
                    return await self._download(session, video_url)
                if status == "failed":
                    raise VideoGenerationError(f"{self.provider_name} üretimi başarısız döndü (job_id={job_id}).")
                await asyncio.sleep(_POLL_INTERVAL_SECONDS)

            raise VideoGenerationError(
                f"{self.provider_name} üretimi zaman aşımına uğradı (job_id={job_id})."
            )

    async def _download(self, session: aiohttp.ClientSession, url: str) -> bytes:
        async with session.get(url) as resp:
            if resp.status != 200:
                raise VideoGenerationError(f"Üretilen video indirilemedi (HTTP {resp.status}).")
            return await resp.read()

    @abc.abstractmethod
    async def _submit(
        self,
        session: aiohttp.ClientSession,
        prompt: str,
        source_image_bytes: bytes | None,
        negative_prompt: str | None,
        aspect_ratio: str,
    ) -> str:
        """Submit the job; return the provider's job/generation id."""

    @abc.abstractmethod
    async def _poll(self, session: aiohttp.ClientSession, job_id: str) -> tuple[str, str | None]:
        """Return (normalized_status, video_url_or_None).

        normalized_status is one of "processing", "completed", "failed".
        """


class LumaDreamMachineService(BaseVideoGenerationService):
    """Luma Labs Dream Machine API integration.

    Docs (verify before production use): https://docs.lumalabs.ai/
    """

    provider_name = "Luma Dream Machine"

    async def _submit(
        self,
        session: aiohttp.ClientSession,
        prompt: str,
        source_image_bytes: bytes | None,
        negative_prompt: str | None,
        aspect_ratio: str,
    ) -> str:
        self._require_configured("LUMA_API_KEY")
        # TODO(production): Luma expects a publicly reachable image URL for
        # image-to-video ("keyframes.frame0.url"), not raw bytes. Upload
        # `source_image_bytes` to temporary object storage first and pass
        # that URL here once real credentials are available.
        payload: dict = {
            "prompt": prompt,
            "aspect_ratio": aspect_ratio,
            "loop": True,
        }
        if negative_prompt:
            payload["negative_prompt"] = negative_prompt

        headers = {"Authorization": f"Bearer {self._api_key}", "Content-Type": "application/json"}
        async with session.post(f"{self._base_url}/generations", json=payload, headers=headers) as resp:
            data = await resp.json()
            if resp.status not in (200, 201):
                raise VideoGenerationError(f"Luma isteği reddedildi (HTTP {resp.status}): {data}")
            job_id = data.get("id")
            if not job_id:
                raise VideoGenerationError(f"Luma yanıtında job id bulunamadı: {data}")
            return job_id

    async def _poll(self, session: aiohttp.ClientSession, job_id: str) -> tuple[str, str | None]:
        headers = {"Authorization": f"Bearer {self._api_key}"}
        async with session.get(f"{self._base_url}/generations/{job_id}", headers=headers) as resp:
            data = await resp.json()
            state = data.get("state")
            if state == "completed":
                video_url = (data.get("assets") or {}).get("video")
                return "completed", video_url
            if state == "failed":
                return "failed", None
            return "processing", None


class RunwayGen3Service(BaseVideoGenerationService):
    """Runway Gen-3 Alpha "image_to_video" API integration.

    Docs (verify before production use): https://docs.dev.runwayml.com/
    """

    provider_name = "Runway Gen-3 Alpha"

    async def _submit(
        self,
        session: aiohttp.ClientSession,
        prompt: str,
        source_image_bytes: bytes | None,
        negative_prompt: str | None,
        aspect_ratio: str,
    ) -> str:
        self._require_configured("RUNWAY_API_KEY")
        # TODO(production): Runway's image_to_video endpoint expects a
        # base64 data-URI or hosted image URL for `promptImage`. Encode
        # `source_image_bytes` accordingly once real credentials exist.
        payload: dict = {
            "model": "gen3a_turbo",
            "promptText": prompt,
            "ratio": aspect_ratio,
        }

        headers = {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
            "X-Runway-Version": "2024-11-06",
        }
        async with session.post(f"{self._base_url}/image_to_video", json=payload, headers=headers) as resp:
            data = await resp.json()
            if resp.status not in (200, 201):
                raise VideoGenerationError(f"Runway isteği reddedildi (HTTP {resp.status}): {data}")
            job_id = data.get("id")
            if not job_id:
                raise VideoGenerationError(f"Runway yanıtında job id bulunamadı: {data}")
            return job_id

    async def _poll(self, session: aiohttp.ClientSession, job_id: str) -> tuple[str, str | None]:
        headers = {"Authorization": f"Bearer {self._api_key}", "X-Runway-Version": "2024-11-06"}
        async with session.get(f"{self._base_url}/tasks/{job_id}", headers=headers) as resp:
            data = await resp.json()
            status = data.get("status")
            if status == "SUCCEEDED":
                outputs = data.get("output") or []
                video_url = outputs[0] if outputs else None
                return "completed", video_url
            if status in ("FAILED", "CANCELLED"):
                return "failed", None
            return "processing", None


def build_video_service(
    provider: str,
    luma_api_key: str | None,
    luma_base_url: str,
    runway_api_key: str | None,
    runway_base_url: str,
    request_timeout_seconds: int = 60,
) -> BaseVideoGenerationService:
    """Factory selecting the configured video provider (see VIDEO_PROVIDER in .env)."""
    if provider == "luma":
        return LumaDreamMachineService(luma_api_key, luma_base_url, request_timeout_seconds)
    if provider == "runway":
        return RunwayGen3Service(runway_api_key, runway_base_url, request_timeout_seconds)
    raise ValueError(f"Unknown video provider: {provider!r}")
