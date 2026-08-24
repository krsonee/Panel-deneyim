"""Alibaba DirectMail — hesap bazlı günlük gönderim kotası.

Limit tüm domain’ler / tenant’lar için ortaktır (Main Account Daily quota).

Sayaç, SMTP’ye gerçekten giden mailleri sayar (sent + fail + Alibaba
real_status). Kuyrukta kalan / hiç gitmeyen skip sayılmaz.

Zaman penceresi: COALESCE(sent_at, created_at) — kuyruk dün, gönderim bugün
ise bugünün kotasına yazılır. Timestamp T/Z/boşluk/+00:00 karışımı normalize edilir.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from database import fetchall, fetchone, get_mail_setting, scalar, upsert_mail_setting

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore

SETTING_LIMIT = "alibaba_daily_quota_limit"
SETTING_TZ = "alibaba_daily_quota_tz"
DEFAULT_LIMIT = 20000
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


def ensure_quota_defaults(conn) -> None:
    """Eski 50k varsayılanını / boş ayarı 20k’ya çeker (bir kez)."""
    raw = (get_mail_setting(conn, SETTING_LIMIT, "") or "").strip()
    if not raw or raw in ("50000", "5000"):
        set_quota_limit(conn, DEFAULT_LIMIT)
    tz_raw = (get_mail_setting(conn, SETTING_TZ, "") or "").strip()
    if not tz_raw:
        set_quota_tz(conn, DEFAULT_TZ)


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


def _norm_bound(iso_s: str) -> str:
    """'2026-08-24T00:00:00Z' → '2026-08-24 00:00:00' (lexicographic TEXT compare)."""
    s = (iso_s or "").replace("T", " ").replace("Z", "")
    s = s.replace("+00:00", "").replace("+00", "")
    return s.strip()


def _norm_ts_sql(expr: str) -> str:
    return (
        "REPLACE(REPLACE(REPLACE(REPLACE("
        f"CAST({expr} AS TEXT), 'T', ' '), 'Z', ''), '+00:00', ''), '+00', '')"
    )


def send_event_ts_sql(alias: str = "") -> str:
    """SMTP anı (sent_at); yoksa created_at."""
    p = f"{alias}." if alias else ""
    return f"COALESCE(NULLIF(TRIM({p}sent_at), ''), {p}created_at)"


# Alibaba kotasına / domain cap’e yazılan gönderimler (SMTP’ye çıktı veya
# Alibaba real_status geldi). queued + hiç gitmeyen skip hariç.
QUOTA_HIT_SQL = """
(
  LOWER(COALESCE(status, '')) NOT IN ('queued', '')
  AND (
    LOWER(status) IN ('sent', 'simulated', 'failed', 'bounced')
    OR COALESCE(real_status, '') IN ('delivered', 'invalid', 'failed', 'spam')
    OR TRIM(COALESCE(provider_msg_id, '')) <> ''
  )
)
"""

FAIL_SQL = """
(
  COALESCE(real_status, '') IN ('invalid', 'failed', 'spam')
  OR LOWER(COALESCE(status, '')) IN ('failed', 'bounced')
)
"""

SUCCESS_SQL = f"""
(
  NOT {FAIL_SQL}
  AND (
    COALESCE(real_status, '') = 'delivered'
    OR LOWER(COALESCE(status, '')) IN ('sent', 'simulated')
  )
)
"""


def window_filter_sql(conn, alias: str = "") -> tuple[str, tuple[str, str]]:
    since, until, _, _ = _day_window(conn)
    ts = _norm_ts_sql(send_event_ts_sql(alias))
    return f"{ts} >= ? AND {ts} < ?", (_norm_bound(since), _norm_bound(until))


def _empty_stats() -> dict:
    return {"used": 0, "success": 0, "fail": 0}


def send_stats_today(conn, *, domain_id: int | None = None) -> dict:
    """Bugünkü kota penceresinde atılan / başarılı / fail."""
    win, params = window_filter_sql(conn)
    extra = ""
    args: list = list(params)
    if domain_id:
        extra = " AND domain_id = ?"
        args.append(int(domain_id))
    row = fetchone(
        conn,
        f"""
        SELECT
          COUNT(*) AS used,
          COALESCE(SUM(CASE WHEN {SUCCESS_SQL} THEN 1 ELSE 0 END), 0) AS success,
          COALESCE(SUM(CASE WHEN {FAIL_SQL} THEN 1 ELSE 0 END), 0) AS fail
        FROM mail_sends
        WHERE {QUOTA_HIT_SQL}
          AND {win}
          {extra}
        """,
        tuple(args),
    )
    if not row:
        return _empty_stats()
    return {
        "used": int(row["used"] or 0),
        "success": int(row["success"] or 0),
        "fail": int(row["fail"] or 0),
    }


def send_stats_today_by_domain(conn, domain_ids: list[int]) -> dict[int, dict]:
    ids = [int(i) for i in domain_ids]
    out = {i: _empty_stats() for i in ids}
    if not ids:
        return out
    win, params = window_filter_sql(conn)
    ph = ",".join(["?"] * len(ids))
    rows = fetchall(
        conn,
        f"""
        SELECT
          domain_id,
          COUNT(*) AS used,
          COALESCE(SUM(CASE WHEN {SUCCESS_SQL} THEN 1 ELSE 0 END), 0) AS success,
          COALESCE(SUM(CASE WHEN {FAIL_SQL} THEN 1 ELSE 0 END), 0) AS fail
        FROM mail_sends
        WHERE domain_id IN ({ph})
          AND {QUOTA_HIT_SQL}
          AND {win}
        GROUP BY domain_id
        """,
        tuple(ids) + tuple(params),
    ) or []
    for r in rows:
        try:
            did = int(r["domain_id"])
        except (TypeError, ValueError, KeyError):
            continue
        out[did] = {
            "used": int(r["used"] or 0),
            "success": int(r["success"] or 0),
            "fail": int(r["fail"] or 0),
        }
    return out


def count_used_today(conn) -> int:
    return send_stats_today(conn)["used"]


def quota_snapshot(conn) -> dict:
    limit = get_quota_limit(conn)
    stats = send_stats_today(conn)
    used = stats["used"]
    remaining = max(0, limit - used)
    since, until, renews_at, tz_name = _day_window(conn)
    pct = round(100.0 * used / limit, 1) if limit else 0.0
    return {
        "limit": limit,
        "used": used,
        "success": stats["success"],
        "fail": stats["fail"],
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
