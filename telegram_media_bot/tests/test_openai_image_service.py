"""Tests for the OpenAI DALL-E 3 / GPT image model compatibility layer.

Regression coverage for the real-world bug where GPT image models
(gpt-image-1 and successors) reject the `response_format` parameter with
`400 Unknown parameter: 'response_format'` — see bot/services/openai_image_service.py
module docstring for the full explanation.
"""

from __future__ import annotations

import base64
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from bot.services.openai_image_service import OpenAIImageService, _supports_response_format
from bot.utils.exceptions import ImageGenerationError, ProviderNotConfiguredError


@pytest.mark.parametrize(
    "model, expected",
    [
        ("dall-e-3", True),
        ("dall-e-2", True),
        ("DALL-E-3", True),
        ("gpt-image-1", False),
        ("gpt-image-1.5", False),
        ("GPT-IMAGE-1", False),
    ],
)
def test_supports_response_format(model: str, expected: bool):
    assert _supports_response_format(model) is expected


def _fake_response(*, b64_json: str | None = None, url: str | None = None):
    return SimpleNamespace(data=[SimpleNamespace(b64_json=b64_json, url=url)])


@pytest.mark.asyncio
async def test_generate_image_raises_when_not_configured():
    service = OpenAIImageService(api_key=None)
    with pytest.raises(ProviderNotConfiguredError):
        await service.generate_image("a prompt")


@pytest.mark.asyncio
async def test_dall_e_3_request_includes_response_format_and_decodes_b64():
    service = OpenAIImageService(api_key="fake-key", model="dall-e-3")
    raw_bytes = b"fake-png-bytes"
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
    assert call_kwargs["model"] == "dall-e-3"
    assert call_kwargs["response_format"] == "b64_json"


@pytest.mark.asyncio
async def test_gpt_image_model_request_omits_response_format():
    """Regression test: sending response_format to gpt-image-1 caused a 400."""
    service = OpenAIImageService(api_key="fake-key", model="gpt-image-1")
    raw_bytes = b"fake-png-bytes-from-gpt-image"
    fake_client = SimpleNamespace(
        images=SimpleNamespace(
            generate=AsyncMock(
                return_value=_fake_response(b64_json=base64.b64encode(raw_bytes).decode())
            )
        )
    )
    service._client = fake_client

    result = await service.generate_image("Aztec Gold Deluxe mascot")

    assert result == raw_bytes
    call_kwargs = fake_client.images.generate.call_args.kwargs
    assert "response_format" not in call_kwargs
    assert call_kwargs["model"] == "gpt-image-1"


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
