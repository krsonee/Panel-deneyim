"""Tests for the OpenAI DALL-E 3 / GPT image model compatibility layer.

Regression coverage for the real-world bug where the Images API rejects
the `response_format` parameter with `400 Unknown parameter:
'response_format'` — see bot/services/openai_image_service.py module
docstring for the full explanation. This has been observed on *both*
`gpt-image-1` (never supported it) and, more recently, real `dall-e-3`
accounts (used to require it, now reject it) — so the fix is to never
send it, plus a generic "drop the offending parameter and retry" safety
net for whatever breaks next.
"""

from __future__ import annotations

import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.services.openai_image_service import OpenAIImageService
from bot.utils.exceptions import ImageGenerationError, ProviderNotConfiguredError


def _fake_response(*, b64_json: str | None = None, url: str | None = None):
    return SimpleNamespace(data=[SimpleNamespace(b64_json=b64_json, url=url)])


def _fake_unknown_parameter_error(param: str) -> Exception:
    """Build an exception shaped like openai's APIError for a 400
    'unknown_parameter' response (has `.code` and `.param` attributes,
    same as the real SDK's BadRequestError)."""
    exc = RuntimeError(f"Unknown parameter: '{param}'.")
    exc.code = "unknown_parameter"  # type: ignore[attr-defined]
    exc.param = param  # type: ignore[attr-defined]
    return exc


@pytest.mark.asyncio
async def test_generate_image_raises_when_not_configured():
    service = OpenAIImageService(api_key=None)
    with pytest.raises(ProviderNotConfiguredError):
        await service.generate_image("a prompt")


@pytest.mark.parametrize("model", ["dall-e-3", "dall-e-2", "gpt-image-1", "gpt-image-1.5"])
@pytest.mark.asyncio
async def test_request_never_includes_response_format(model: str):
    """response_format has been rejected by both dall-e-3 and gpt-image-*
    accounts in the wild — it must never be sent, regardless of model."""
    service = OpenAIImageService(api_key="fake-key", model=model)
    raw_bytes = b"fake-image-bytes"
    fake_client = SimpleNamespace(
        images=SimpleNamespace(
            generate=AsyncMock(
                return_value=_fake_response(b64_json=base64.b64encode(raw_bytes).decode())
            )
        )
    )
    service._client = fake_client  # bypass real AsyncOpenAI construction

    result = await service.generate_image("Aztec Gold Deluxe mascot")

    assert result == raw_bytes
    call_kwargs = fake_client.images.generate.call_args.kwargs
    assert "response_format" not in call_kwargs
    assert call_kwargs["model"] == model


@pytest.mark.asyncio
async def test_falls_back_to_downloading_url_when_no_b64_json(monkeypatch):
    service = OpenAIImageService(api_key="fake-key", model="dall-e-3")
    fake_client = SimpleNamespace(
        images=SimpleNamespace(
            generate=AsyncMock(return_value=_fake_response(url="https://example.com/img.png"))
        )
    )
    service._client = fake_client

    download_mock = AsyncMock(return_value=b"downloaded-bytes")
    monkeypatch.setattr(service, "_download", download_mock)

    result = await service.generate_image("a prompt")

    assert result == b"downloaded-bytes"
    download_mock.assert_awaited_once_with("https://example.com/img.png")


@pytest.mark.asyncio
async def test_raises_image_generation_error_when_response_has_neither_field():
    service = OpenAIImageService(api_key="fake-key", model="dall-e-3")
    fake_client = SimpleNamespace(
        images=SimpleNamespace(generate=AsyncMock(return_value=_fake_response()))
    )
    service._client = fake_client

    with pytest.raises(ImageGenerationError):
        await service.generate_image("a prompt")


@pytest.mark.asyncio
async def test_unknown_parameter_error_triggers_drop_and_retry_fallback():
    """If the API ever rejects one of *our* other parameters (e.g. `size`)
    as unknown, the request should self-heal by dropping it and retrying
    once, instead of failing the whole generation."""
    service = OpenAIImageService(api_key="fake-key", model="dall-e-3", size="1024x1024")
    raw_bytes = b"fake-image-bytes"
    generate_mock = AsyncMock(
        side_effect=[
            _fake_unknown_parameter_error("size"),
            _fake_response(b64_json=base64.b64encode(raw_bytes).decode()),
        ]
    )
    fake_client = SimpleNamespace(images=SimpleNamespace(generate=generate_mock))
    service._client = fake_client

    result = await service.generate_image("a prompt")

    assert result == raw_bytes
    assert generate_mock.await_count == 2
    first_call_kwargs = generate_mock.call_args_list[0].kwargs
    retry_call_kwargs = generate_mock.call_args_list[1].kwargs
    assert "size" in first_call_kwargs
    assert "size" not in retry_call_kwargs


@pytest.mark.asyncio
async def test_unknown_parameter_error_for_untracked_param_is_not_swallowed(monkeypatch):
    """If the rejected param isn't even one we sent, don't silently retry
    forever — surface it as a real failure after the normal retry budget."""
    service = OpenAIImageService(api_key="fake-key", model="dall-e-3")
    generate_mock = AsyncMock(side_effect=_fake_unknown_parameter_error("some_future_param"))
    fake_client = SimpleNamespace(images=SimpleNamespace(generate=generate_mock))
    service._client = fake_client

    async def _no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("bot.services.openai_image_service.asyncio.sleep", _no_sleep)

    with pytest.raises(ImageGenerationError):
        await service.generate_image("a prompt")


@pytest.mark.asyncio
async def test_retries_then_raises_on_repeated_provider_errors(monkeypatch):
    service = OpenAIImageService(api_key="fake-key", model="dall-e-3")
    fake_client = SimpleNamespace(
        images=SimpleNamespace(generate=AsyncMock(side_effect=RuntimeError("boom")))
    )
    service._client = fake_client

    async def _no_sleep(_seconds: float) -> None:
        return None

    monkeypatch.setattr("bot.services.openai_image_service.asyncio.sleep", _no_sleep)

    with pytest.raises(ImageGenerationError):
        await service.generate_image("a prompt")

    assert fake_client.images.generate.await_count == 3  # initial attempt + 2 retries
