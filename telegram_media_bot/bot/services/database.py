"""aiosqlite connection lifecycle and schema management.

A single shared aiosqlite connection is opened at startup and closed at
shutdown (see bot/loader.py). aiosqlite serializes access internally, so
one connection is sufficient for a bot with a small whitelisted user base.
"""

from __future__ import annotations

import logging
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)

_SCHEMA = """
CREATE TABLE IF NOT EXISTS usage_daily (
    user_id     INTEGER NOT NULL,
    usage_date  TEXT    NOT NULL,   -- ISO date, e.g. 2026-09-22, in UTC
    kind        TEXT    NOT NULL,   -- 'image' | 'video' | 'sticker'
    count       INTEGER NOT NULL DEFAULT 0,
    PRIMARY KEY (user_id, usage_date, kind)
);

CREATE TABLE IF NOT EXISTS generation_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id     INTEGER NOT NULL,
    created_at  TEXT    NOT NULL,   -- ISO 8601 UTC timestamp
    category    TEXT    NOT NULL,   -- 'casino' | 'sports'
    theme       TEXT    NOT NULL,
    output_type TEXT    NOT NULL,   -- 'image' | 'video' | 'sticker'
    prompt      TEXT    NOT NULL,
    status      TEXT    NOT NULL,   -- 'ok' | 'error'
    error       TEXT
);
"""


async def open_database(database_path: Path) -> aiosqlite.Connection:
    """Open the aiosqlite connection and ensure the schema exists."""
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = await aiosqlite.connect(database_path)
    connection.row_factory = aiosqlite.Row
    await connection.executescript(_SCHEMA)
    await connection.commit()
    logger.info("Veritabanı hazır: %s", database_path)
    return connection


async def close_database(connection: aiosqlite.Connection) -> None:
    await connection.close()
    logger.info("Veritabanı bağlantısı kapatıldı.")
