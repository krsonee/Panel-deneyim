"""Tests for the casino/sports prompt engineering module."""

from __future__ import annotations

from bot.utils.constants import CasinoTheme, OutputType, SportsTheme
from bot.utils.prompt_builder import (
    build_casino_prompt,
    build_prompt_for_casino,
    build_prompt_for_sports,
    build_sports_prompt,
    build_sticker_prompt,
    build_video_motion_prompt,
)


def test_casino_prompt_contains_subject_and_house_style():
    prompt = build_casino_prompt(CasinoTheme.SLOT_KEY_ART, "Aztec Gold Deluxe")
    assert "Aztec Gold Deluxe" in prompt
    assert "gold" in prompt.lower()
    assert "royal blue" in prompt.lower()


def test_casino_prompt_includes_custom_details():
    prompt = build_casino_prompt(CasinoTheme.MASCOT_3D, "Jungle Tiger", custom_details="wearing a crown")
    assert "wearing a crown" in prompt


def test_every_casino_theme_produces_distinct_core_concept():
    prompts = {theme: build_casino_prompt(theme, "Test Slot") for theme in CasinoTheme}
    assert len(set(prompts.values())) == len(CasinoTheme)


def test_sports_prompt_contains_subject():
    prompt = build_sports_prompt(SportsTheme.MATCHDAY_BANNER, "Galatasaray vs Fenerbahce")
    assert "Galatasaray vs Fenerbahce" in prompt


def test_every_sports_theme_produces_distinct_core_concept():
    prompts = {theme: build_sports_prompt(theme, "Test Match") for theme in SportsTheme}
    assert len(set(prompts.values())) == len(SportsTheme)


def test_sticker_prompt_adds_isolation_instructions():
    base = build_casino_prompt(CasinoTheme.MASCOT_3D, "Tiger Slot")
    sticker_prompt = build_sticker_prompt(base)
    assert "isolated" in sticker_prompt.lower()
    assert base.split(",")[0] in sticker_prompt


def test_video_motion_prompt_adds_motion_direction():
    base = build_casino_prompt(CasinoTheme.FREESPIN_RAIN, "Coin Slot")
    video_prompt = build_video_motion_prompt(base, theme=CasinoTheme.FREESPIN_RAIN)
    assert "animation direction" in video_prompt.lower()
    assert "loop" in video_prompt.lower()


def test_build_prompt_for_casino_sticker_applies_isolation_layer():
    result = build_prompt_for_casino(CasinoTheme.SLOT_KEY_ART, "Gold Slot", OutputType.STICKER)
    assert result.output_type is OutputType.STICKER
    assert "isolated" in result.positive_prompt.lower()


def test_build_prompt_for_sports_video_applies_motion_layer():
    result = build_prompt_for_sports(SportsTheme.LIVE_ACTION, "Football Derby", OutputType.VIDEO)
    assert result.output_type is OutputType.VIDEO
    assert "animation direction" in result.positive_prompt.lower()


def test_build_prompt_for_casino_image_has_no_extra_layers():
    result = build_prompt_for_casino(CasinoTheme.JACKPOT_BANNER, "Mega Slot", OutputType.IMAGE)
    assert "animation direction" not in result.positive_prompt.lower()
    assert "isolated" not in result.positive_prompt.lower()
