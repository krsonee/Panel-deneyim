"""Aggregates all handler routers and registers them onto the Dispatcher."""

from __future__ import annotations

from aiogram import Dispatcher

from bot.handlers import casino, fallback, generation, menu, quota, sports, start


def register_handlers(dp: Dispatcher) -> None:
    """Include every router in the correct precedence order.

    Order matters: aiogram tries routers top-to-bottom and the first
    matching handler wins, so `fallback` (a no-filter catch-all) must be
    included last.
    """
    dp.include_router(start.router)
    dp.include_router(menu.router)
    dp.include_router(casino.router)
    dp.include_router(sports.router)
    dp.include_router(generation.router)
    dp.include_router(quota.router)
    dp.include_router(fallback.router)
