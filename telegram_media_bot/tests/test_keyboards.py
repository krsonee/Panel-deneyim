"""Smoke tests: every keyboard builds valid markup and callback_data round-trips."""

from __future__ import annotations

from aiogram.types import InlineKeyboardMarkup

from bot.keyboards.callback_data import CasinoThemeCallback, MainMenuCallback, OutputTypeCallback
from bot.keyboards.confirm_menu import build_confirm_menu
from bot.keyboards.main_menu import build_back_to_menu_keyboard, build_main_menu
from bot.keyboards.output_menu import build_output_type_menu, build_skip_details_keyboard
from bot.keyboards.theme_menus import build_casino_theme_menu, build_sports_theme_menu
from bot.utils.constants import CasinoTheme


def test_main_menu_is_valid_markup_with_expected_actions():
    markup = build_main_menu()
    assert isinstance(markup, InlineKeyboardMarkup)
    actions = {
        MainMenuCallback.unpack(button.callback_data).action
        for row in markup.inline_keyboard
        for button in row
    }
    assert {"casino", "sports", "quota", "help"} <= actions


def test_casino_theme_menu_covers_every_theme():
    markup = build_casino_theme_menu()
    themes = {
        CasinoThemeCallback.unpack(button.callback_data).theme
        for row in markup.inline_keyboard
        for button in row
    }
    assert themes == {theme.value for theme in CasinoTheme}


def test_sports_theme_menu_builds():
    markup = build_sports_theme_menu()
    assert isinstance(markup, InlineKeyboardMarkup)
    assert len(markup.inline_keyboard) > 0


def test_output_type_menu_round_trips_callback_data():
    markup = build_output_type_menu()
    for row in markup.inline_keyboard:
        for button in row:
            unpacked = OutputTypeCallback.unpack(button.callback_data)
            assert unpacked.output_type


def test_confirm_menu_and_misc_keyboards_build_without_error():
    assert isinstance(build_confirm_menu(), InlineKeyboardMarkup)
    assert isinstance(build_skip_details_keyboard(), InlineKeyboardMarkup)
    assert isinstance(build_back_to_menu_keyboard(), InlineKeyboardMarkup)
