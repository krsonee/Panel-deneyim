"""Centralized logging setup used by main.py and tests."""

from __future__ import annotations

import logging
import sys

_CONFIGURED = False


def setup_logging(level: str = "INFO") -> None:
    """Configure the root logger once with a consistent, readable format.

    Safe to call multiple times (e.g. from tests) — subsequent calls are
    no-ops so handlers are never duplicated.
    """
    global _CONFIGURED
    if _CONFIGURED:
        return

    handler = logging.StreamHandler(sys.stdout)
    formatter = logging.Formatter(
        fmt="%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )
    handler.setFormatter(formatter)

    root = logging.getLogger()
    root.addHandler(handler)
    root.setLevel(level)

    # aiogram/aiohttp/openai are chatty at DEBUG; keep them quieter unless the
    # operator explicitly asked for DEBUG-level logs.
    if level != "DEBUG":
        logging.getLogger("aiogram").setLevel(logging.INFO)
        logging.getLogger("aiohttp").setLevel(logging.WARNING)
        logging.getLogger("openai").setLevel(logging.WARNING)
        logging.getLogger("httpx").setLevel(logging.WARNING)

    _CONFIGURED = True
