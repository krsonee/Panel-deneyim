"""Per-user daily quota tracking backed by aiosqlite.

Each (user_id, date, kind) triple has its own counter that resets
naturally at UTC midnight simply because a new date produces a fresh row.
No cron/reset job is needed.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import datetime, timezone

import aiosqlite

from bot.utils.exceptions import QuotaExceededError

logger = logging.getLogger(__name__)


def _today() -> str:
    return datetime.now(timezone.utc).date().isoformat()


@dataclass(frozen=True, slots=True)
class QuotaStatus:
    kind: str
    used: int
    limit: int

    @property
    def remaining(self) -> int:
        return max(self.limit - self.used, 0)

    @property
    def is_exceeded(self) -> bool:
        return self.used >= self.limit


class QuotaService:
    """Reads and increments per-user, per-kind daily usage counters."""

    def __init__(self, connection: aiosqlite.Connection, limits: dict[str, int]):
        self._connection = connection
        self._limits = limits

    def limit_for(self, kind: str) -> int:
        return self._limits.get(kind, 0)

    async def get_status(self, user_id: int, kind: str, *, usage_date: str | None = None) -> QuotaStatus:
        usage_date = usage_date or _today()
        cursor = await self._connection.execute(
            "SELECT count FROM usage_daily WHERE user_id = ? AND usage_date = ? AND kind = ?",
            (user_id, usage_date, kind),
        )
        row = await cursor.fetchone()
        used = row["count"] if row else 0
        return QuotaStatus(kind=kind, used=used, limit=self.limit_for(kind))

    async def get_all_status(self, user_id: int) -> list[QuotaStatus]:
        return [await self.get_status(user_id, kind) for kind in sorted(self._limits)]

    async def check_and_increment(self, user_id: int, kind: str) -> QuotaStatus:
        """Atomically check the daily limit and increment on success.

        Raises:
            QuotaExceededError: if the user has already used up today's
                allowance for this ``kind``.
        """
        usage_date = _today()
        status = await self.get_status(user_id, kind, usage_date=usage_date)
        if status.is_exceeded:
            logger.info(
                "Kota aşıldı: user_id=%s kind=%s used=%s limit=%s",
                user_id,
                kind,
                status.used,
                status.limit,
            )
            raise QuotaExceededError(kind=kind, limit=status.limit, used=status.used)

        await self._connection.execute(
            """
            INSERT INTO usage_daily (user_id, usage_date, kind, count)
            VALUES (?, ?, ?, 1)
            ON CONFLICT(user_id, usage_date, kind)
            DO UPDATE SET count = count + 1
            """,
            (user_id, usage_date, kind),
        )
        await self._connection.commit()
        return QuotaStatus(kind=kind, used=status.used + 1, limit=status.limit)

    async def log_generation(
        self,
        user_id: int,
        category: str,
        theme: str,
        output_type: str,
        prompt: str,
        status: str,
        error: str | None = None,
    ) -> None:
        """Append an audit row for every generation attempt (success or failure)."""
        await self._connection.execute(
            """
            INSERT INTO generation_log
                (user_id, created_at, category, theme, output_type, prompt, status, error)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                user_id,
                datetime.now(timezone.utc).isoformat(),
                category,
                theme,
                output_type,
                prompt,
                status,
                error,
            ),
        )
        await self._connection.commit()
