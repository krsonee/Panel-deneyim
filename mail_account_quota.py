"""Alibaba DirectMail — hesap bazlı günlük gönderim kotası.

Limit tüm domain’ler / tenant’lar için ortaktır (Main Account Daily quota).

Sayaç, SMTP’ye gerçekten giden mailleri sayar (sent + fail + Alibaba
real_status). Kuyrukta kalan / hiç gitmeyen skip sayılmaz.

Zaman penceresi raporlarla aynı: CAST(created_at/sent_at AS TEXT) >= 'YYYY-MM-DD'.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from database import (
    fetchall,
    fetchone,
    get_mail_setting,
    row_get,
    safe_rollback,
    scalar,
    upsert_mail_setting,
    uses_postgres,
)

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore

SETTING_LIMIT = "alibaba_daily_quota_limit"
SETTING_TZ = "alibaba_daily_quota_tz"
DEFAULT_LIMIT = 20000
# DirectMail SG / global hesaplarda günlük reset genelde UTC gece yarısı
DEFAULT_TZ = "UTC"
# Karttaki «bugün» = operatör günü (TR). Alibaba UTC 00:00 reset hâlâ yenilenme satırında.
DISPLAY_TZ = "Europe/Istanbul"


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


def ensure_quota_defaults(conn) -> None:
    """Eski 50k varsayılanını / boş ayarı 20k’ya çeker (bir kez)."""
    raw = (get_mail_setting(conn, SETTING_LIMIT, "") or "").strip()
    if not raw or raw in ("50000", "5000"):
        set_quota_limit(conn, DEFAULT_LIMIT)
    tz_raw = (get_mail_setting(conn, SETTING_TZ, "") or "").strip()
    if not tz_raw:
        set_quota_tz(conn, DEFAULT_TZ)


def _day_window_tz(tz_name: str) -> tuple[str, str, datetime, str]:
    z = _zone(tz_name)
    now = datetime.now(timezone.utc).astimezone(z)
    start_local = now.replace(hour=0, minute=0, second=0, microsecond=0)
    end_local = start_local + timedelta(days=1)
    since = start_local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    until = end_local.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    return since, until, end_local, tz_name


def _day_window(conn) -> tuple[str, str, datetime, str]:
    """Alibaba kota TZ (varsayılan UTC) — kapı/yenilenme."""
    return _day_window_tz(get_quota_tz_name(conn))


def _display_day_window(_conn=None) -> tuple[str, str, datetime, str]:
    """Panel «bugün» = Europe/Istanbul takvim günü."""
    return _day_window_tz(DISPLAY_TZ)


QUOTA_HIT_SQL = """
(
  LOWER(COALESCE(status, '')) IN ('sent', 'simulated', 'failed', 'bounced', 'queued')
  OR COALESCE(real_status, '') IN ('delivered', 'invalid', 'failed', 'spam')
)
"""

FAIL_SQL = """
(
  COALESCE(real_status, '') IN ('invalid', 'failed', 'spam')
  OR LOWER(COALESCE(status, '')) IN ('failed', 'bounced')
)
"""

SUCCESS_SQL = """
(
  COALESCE(real_status, '') NOT IN ('invalid', 'failed', 'spam')
  AND LOWER(COALESCE(status, '')) NOT IN ('failed', 'bounced', 'queued')
  AND (
    COALESCE(real_status, '') = 'delivered'
    OR LOWER(COALESCE(status, '')) IN ('sent', 'simulated')
  )
)
"""

QUEUED_SQL = """
(
  LOWER(COALESCE(status, '')) = 'queued'
)
"""


def _event_ts_sql(alias: str = "") -> str:
    p = f"{alias}." if alias else ""
    if uses_postgres():
        return (
            f"COALESCE("
            f"NULLIF(BTRIM(CAST({p}sent_at AS TEXT)), '')::timestamptz, "
            f"{p}created_at::timestamptz)"
        )
    return f"COALESCE(NULLIF(TRIM(CAST({p}sent_at AS TEXT)), ''), {p}created_at)"


def window_filter_sql(conn=None, alias: str = "", *, since: str | None = None, until: str | None = None) -> tuple[str, tuple]:
    """since/until: UTC ISO. Verilmezse panel günü (TR 00:00)."""
    if not since or not until:
        since, until, _, _ = _display_day_window(conn)
    ev = _event_ts_sql(alias)
    if uses_postgres():
        return f"({ev} >= ?::timestamptz AND {ev} < ?::timestamptz)", (since, until)
    return f"(datetime({ev}) >= datetime(?) AND datetime({ev}) < datetime(?))", (since, until)


def _empty_stats() -> dict:
    return {"used": 0, "success": 0, "fail": 0, "queued": 0}


def _row_to_stats(row) -> dict:
    if not row:
        return _empty_stats()
    used = int(row_get(row, "used") or 0)
    success = int(row_get(row, "success") or 0)
    fail = int(row_get(row, "fail") or 0)
    queued = int(row_get(row, "queued") or 0)
    if queued <= 0:
        queued = max(0, used - success - fail)
    return {"used": used, "success": success, "fail": fail, "queued": queued}


def send_stats_in_window(conn, since: str, until: str, *, domain_id: int | None = None) -> dict:
    win, params = window_filter_sql(conn, since=since, until=until)
    extra = ""
    args: list = list(params)
    if domain_id:
        extra = " AND domain_id = ?"
        args.append(int(domain_id))
    sql = f"""
        SELECT
          COUNT(*) AS used,
          COALESCE(SUM(CASE WHEN {SUCCESS_SQL} THEN 1 ELSE 0 END), 0) AS success,
          COALESCE(SUM(CASE WHEN {FAIL_SQL} THEN 1 ELSE 0 END), 0) AS fail,
          COALESCE(SUM(CASE WHEN {QUEUED_SQL} THEN 1 ELSE 0 END), 0) AS queued
        FROM mail_sends
        WHERE {QUOTA_HIT_SQL}
          AND {win}
          {extra}
    """
    try:
        row = fetchone(conn, sql, tuple(args))
        return _row_to_stats(row)
    except Exception as exc:
        print(f"⚠️  send_stats_in_window: {exc}")
        safe_rollback(conn)
        extra_fb = ""
        args_fb: list = [since, until]
        if domain_id:
            extra_fb = " AND domain_id = ?"
            args_fb.append(int(domain_id))
        try:
            row = fetchone(
                conn,
                f"""
                SELECT
                  COUNT(*) AS used,
                  COALESCE(SUM(CASE WHEN {SUCCESS_SQL} THEN 1 ELSE 0 END), 0) AS success,
                  COALESCE(SUM(CASE WHEN {FAIL_SQL} THEN 1 ELSE 0 END), 0) AS fail,
                  COALESCE(SUM(CASE WHEN {QUEUED_SQL} THEN 1 ELSE 0 END), 0) AS queued
                FROM mail_sends
                WHERE {QUOTA_HIT_SQL}
                  AND CAST(COALESCE(sent_at, created_at) AS TEXT) >= ?
                  AND CAST(COALESCE(sent_at, created_at) AS TEXT) < ?
                  {extra_fb}
                """,
                tuple(args_fb),
            )
            return _row_to_stats(row)
        except Exception as exc2:
            print(f"⚠️  send_stats_in_window fallback: {exc2}")
            safe_rollback(conn)
            return _empty_stats()


def send_stats_today(conn, *, domain_id: int | None = None) -> dict:
    """Karttaki bugün = TR takvim günü."""
    since, until, _, _ = _display_day_window(conn)
    return send_stats_in_window(conn, since, until, domain_id=domain_id)


def send_stats_today_by_domain(conn, domain_ids: list[int]) -> dict[int, dict]:
    ids = [int(i) for i in domain_ids]
    out = {i: _empty_stats() for i in ids}
    if not ids:
        return out
    win, params = window_filter_sql(conn)
    ph = ",".join(["?"] * len(ids))
    try:
        rows = fetchall(
            conn,
            f"""
            SELECT
              domain_id,
              COUNT(*) AS used,
              COALESCE(SUM(CASE WHEN {SUCCESS_SQL} THEN 1 ELSE 0 END), 0) AS success,
              COALESCE(SUM(CASE WHEN {FAIL_SQL} THEN 1 ELSE 0 END), 0) AS fail,
              COALESCE(SUM(CASE WHEN {QUEUED_SQL} THEN 1 ELSE 0 END), 0) AS queued
            FROM mail_sends
            WHERE domain_id IN ({ph})
              AND {QUOTA_HIT_SQL}
              AND {win}
            GROUP BY domain_id
            """,
            tuple(ids) + tuple(params),
        ) or []
    except Exception as exc:
        print(f"⚠️  send_stats_today_by_domain: {exc}")
        safe_rollback(conn)
        return out
    for r in rows:
        try:
            did = int(row_get(r, "domain_id"))
        except (TypeError, ValueError):
            continue
        out[did] = _row_to_stats(r)
    return out


def count_used_today(conn) -> int:
    return send_stats_today(conn)["used"]


def _parse_ts(value):
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    text = str(value).strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        if " " in text and "T" not in text:
            text = text.replace(" ", "T", 1)
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(timezone.utc)
    except Exception:
        return None


def _fmt_tr(value) -> str:
    dt = _parse_ts(value)
    if not dt:
        return str(value or "")[:19]
    return dt.astimezone(_zone(DISPLAY_TZ)).strftime("%d.%m.%Y %H:%M") + " TR"


def quota_snapshot(conn) -> dict:
    limit = get_quota_limit(conn)
    stats = send_stats_today(conn)
    used = stats["used"]
    remaining = max(0, limit - used)
    since_d, until_d, display_end, display_tz = _display_day_window(conn)
    _, _, renews_at, quota_tz = _day_window(conn)
    pct = round(100.0 * used / limit, 1) if limit else 0.0
    last_status = ""
    last_at = ""
    last_label = ""
    recent = []
    try:
        rows = fetchall(
            conn,
            """
            SELECT id, status, created_at, sent_at
            FROM mail_sends
            ORDER BY id DESC
            LIMIT 5
            """,
        ) or []
        for r in rows:
            when = row_get(r, "sent_at") or row_get(r, "created_at") or ""
            st = str(row_get(r, "status") or "")
            recent.append({
                "id": row_get(r, "id"),
                "status": st,
                "when": _fmt_tr(when),
            })
        if rows:
            last_status = str(row_get(rows[0], "status") or "")
            last_at = str(row_get(rows[0], "sent_at") or row_get(rows[0], "created_at") or "")
            last_label = _fmt_tr(last_at)
    except Exception as exc:
        print(f"⚠️  quota last_send: {exc}")
        safe_rollback(conn)
    return {
        "limit": limit,
        "used": used,
        "success": stats["success"],
        "fail": stats["fail"],
        "queued": stats.get("queued") or 0,
        "remaining": remaining,
        "pct_used": pct,
        "exhausted": remaining <= 0,
        "tz": display_tz,
        "quota_tz": quota_tz,
        "window_start_utc": since_d,
        "window_end_utc": until_d,
        "renews_at": renews_at.isoformat(),
        "renews_at_label": renews_at.strftime("%d.%m.%Y %H:%M") + f" ({quota_tz})",
        "display_day_end_label": display_end.strftime("%d.%m.%Y 00:00") + f" ({display_tz})",
        "last_send_at": last_at,
        "last_send_status": last_status,
        "last_send_label": last_label,
        "recent_sends": recent,
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
