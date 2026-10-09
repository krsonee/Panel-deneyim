"""Tests for environment-variable driven configuration loading."""

from __future__ import annotations

import pytest

from bot.config import ConfigError, load_settings


def _write_env(tmp_path, content: str):
    env_file = tmp_path / ".env"
    env_file.write_text(content)
    return env_file


def test_missing_bot_token_raises_config_error(tmp_path, monkeypatch):
    monkeypatch.delenv("BOT_TOKEN", raising=False)
    env_file = _write_env(tmp_path, "WHITELISTED_USER_IDS=111\n")
    with pytest.raises(ConfigError):
        load_settings(env_file)


def test_valid_env_loads_expected_defaults(tmp_path, monkeypatch):
    for key in ("BOT_TOKEN", "WHITELISTED_USER_IDS", "VIDEO_PROVIDER"):
        monkeypatch.delenv(key, raising=False)
    env_file = _write_env(
        tmp_path,
        "BOT_TOKEN=123:abc\n"
        "WHITELISTED_USER_IDS=111, 222 ,not-a-number\n"
        f"DATABASE_PATH={tmp_path / 'bot.db'}\n"
        f"MEDIA_TMP_DIR={tmp_path / 'tmp'}\n",
    )
    settings = load_settings(env_file)

    assert settings.bot_token == "123:abc"
    assert settings.whitelisted_user_ids == frozenset({111, 222})
    assert settings.daily_image_quota == 20
    assert settings.video_provider == "luma"
    assert settings.is_whitelist_configured


def test_invalid_video_provider_raises_config_error(tmp_path, monkeypatch):
    for key in ("BOT_TOKEN", "VIDEO_PROVIDER"):
        monkeypatch.delenv(key, raising=False)
    env_file = _write_env(
        tmp_path,
        "BOT_TOKEN=123:abc\nVIDEO_PROVIDER=not_a_real_provider\n"
        f"DATABASE_PATH={tmp_path / 'bot.db'}\n"
        f"MEDIA_TMP_DIR={tmp_path / 'tmp'}\n",
    )
    with pytest.raises(ConfigError):
        load_settings(env_file)
