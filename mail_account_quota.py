"""Alibaba DirectMail — hesap bazlı günlük gönderim kotası.

Limit tüm domain’ler / tenant’lar için ortaktır (Main Account Daily quota).
Kullanım: mail_sends içinde status sent|simulated (bugün, kota TZ).
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from database import fetchone, get_mail_setting, scalar, upsert_mail_setting

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore

SETTING_LIMIT = "alibaba_daily_quota_limit"
SETTING_TZ = "alibaba_daily_quota_tz"
DEFAULT_LIMIT = 50000
# DirectMail SG / global hesaplarda günlük reset genelde UTC gece yarısı
DEFAULT_TZ = "UTC"


def _zone(name: str):
    if ZoneInfo is None:
        return timezone.utc
    try:
        return ZoneInfo(name or DEFAULT_TZ)
    except Exception:
        return timezone.utc


def get_quota_limit(conn) -> int:
    raw = (get_mail_setting(conn, SETTING_LIMIT, str(DEFAULT_LIMIT)) or "").strip()
    try:
        n = int(raw)
    except (TypeError, ValueError):
        n = DEFAULT_LIMIT
    return max(100, min(n, 5_000_000))


def get_quota_tz_name(conn) -> str:
    return (get_mail_setting(conn, SETTING_TZ, DEFAULT_TZ) or DEFAULT_TZ).strip() or DEFAULT_TZ


def set_quota_limit(conn, limit: int) -> int:
    n = max(100, min(int(limit), 5_000_000))
    upsert_mail_setting(conn, SETTING_LIMIT, str(n))
    return n


def set_quota_tz(conn, tz_name: str) -> str:
    name = (tz_name or DEFAULT_TZ).strip() or DEFAULT_TZ
    if ZoneInfo is not None:
        try:
            ZoneInfo(name)
        except Exception as exc:
            raise ValueError(f"Geçersiz timezone: {name}") from exc
    upsert_mail_setting(conn, SETTING_TZ, name)
    return name


def _day_window(conn) -> tuple[str, str, datetime, str]:
    """Returns (since_iso_utc, until_iso_utc, renews_at_aware, tz_name)."""
    tz_name = get_quota_tz_name(conn)
    z = _zone(tz_name)
    now = datetime.now(timezone.utc).astimezone(z)
    start_local = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)
    since = start_local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    until = end_local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return since, until, end_local, tz_name


def count_used_today(conn) -> int:
    since, until, _, _ = _day_window(conn)
    n = scalar(
        conn,
        """
        SELECT COUNT(*) FROM mail_sends
        WHERE status IN ('sent', 'simulated')
          AND created_at >= ?
          AND created_at < ?
        """,
        (since, until),
    )
    return int(n or 0)


def quota_snapshot(conn) -> dict:
    limit = get_quota_limit(conn)
    used = count_used_today(conn)
    remaining = max(0, limit - used)
    since, until, renews_at, tz_name = _day_window(conn)
    pct = round(100.0 * used / limit, 1) if limit else 0.0
    return {
        "limit": limit,
        "used": used,
        "remaining": remaining,
        "pct_used": pct,
        "exhausted": remaining <= 0,
        "tz": tz_name,
        "window_start_utc": since,
        "window_end_utc": until,
        "renews_at": renews_at.isoformat(),
        "renews_at_label": renews_at.strftime("%d.%m.%Y %H:%M") + f" ({tz_name})",
        "source": "alibaba_account_daily",
    }


def can_queue(conn, pending_count: int) -> tuple[bool, str, dict]:
    """Kampanya kuyruğa alınabilir mi? pending_count kadar slot gerekir."""
    snap = quota_snapshot(conn)
    need = max(0, int(pending_count or 0))
    if need <= 0:
        return True, "", snap
    if snap["remaining"] <= 0:
        return (
            False,
            (
                f"Alibaba günlük kota doldu ({snap['used']}/{snap['limit']}). "
                f"Yenilenme: {snap['renews_at_label']}"
            ),
            snap,
        )
    if need > snap["remaining"]:
        return (
            False,
            (
                f"Alibaba günlük kalan kota yetersiz: kalan {snap['remaining']}, "
                f"kampanya {need} alıcı (limit {snap['limit']}). "
                f"Yenilenme: {snap['renews_at_label']}"
            ),
            snap,
        )
    return True, "", snap


def account_quota_blocks_send(conn) -> tuple[bool, str]:
    """Tek mail gönderiminde hesap kotası bitti mi?"""
    snap = quota_snapshot(conn)
    if snap["remaining"] <= 0:
        return True, f"Alibaba günlük kota doldu ({snap['used']}/{snap['limit']})"
    return False, ""
