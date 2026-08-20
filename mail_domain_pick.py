"""Tenant kampanyaları için otomatik domain seçimi / kapasite.

Firma domain seçmez — tahsisli, sağlıklı, günlük cap’i kalan domainler
arasında rotasyon. Isıtma programının yazdığı daily_cap yakıtıdır.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from database import execute, fetchall, fetchone, scalar

try:
    from zoneinfo import ZoneInfo
    OP_TZ = ZoneInfo("Europe/Istanbul")
except Exception:
    OP_TZ = timezone(timedelta(hours=3))

WARM_RANK = {
    "warm": 3,
    "warming": 2,
    "cold": 1,
    "paused": 0,
    "burned": 0,
}


def day_since_iso_utc() -> str:
    """Europe/Istanbul gün başlangıcı → UTC ISO (domain_is_send_blocked ile aynı)."""
    now_local = datetime.now(OP_TZ)
    day_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
    return day_start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def ensure_auto_domain_column(conn) -> None:
    from database import _table_columns

    cols = _table_columns(conn, "mail_campaigns") or set()
    if "auto_domain" not in cols:
        try:
            execute(
                conn,
                "ALTER TABLE mail_campaigns ADD COLUMN auto_domain INTEGER NOT NULL DEFAULT 0",
            )
        except Exception:
            pass


def domain_sent_today(conn, domain_id: int) -> int:
    since = day_since_iso_utc()
    return int(
        scalar(
            conn,
            """
            SELECT COUNT(*) FROM mail_sends
            WHERE domain_id = ?
              AND status IN ('sent', 'simulated')
              AND created_at >= ?
            """,
            (int(domain_id), since),
        )
        or 0
    )


def domain_remaining_today(conn, domain_row) -> int:
    """Kalan günlük slot. daily_cap<=0 → 0 (güvenli: sınırsız sayma)."""
    cap = int(domain_row.get("daily_cap") or 0)
    if cap <= 0:
        return 0
    sent = domain_sent_today(conn, int(domain_row["id"]))
    return max(0, cap - sent)


def _pool_domains(conn, tenant_id: int | None) -> list[dict]:
    from mail_tenant import domain_has_smtp, list_allocated_domains

    if tenant_id:
        rows = list_allocated_domains(conn, int(tenant_id)) or []
    else:
        rows = fetchall(conn, "SELECT * FROM mail_domains ORDER BY id ASC") or []
    out = []
    for r in rows:
        d = dict(r)
        if not domain_has_smtp(d):
            continue
        out.append(d)
    return out


def list_sendable_domains(
    conn,
    tenant_id: int | None,
    *,
    exclude_ids: set[int] | None = None,
) -> list[dict]:
    """paused/burned/cap-dolu hariç, kalan slotu olan domainler."""
    from mail_domain_health import domain_is_send_blocked

    exclude_ids = exclude_ids or set()
    out = []
    for d in _pool_domains(conn, tenant_id):
        did = int(d["id"])
        if did in exclude_ids:
            continue
        st = (d.get("warm_status") or "").strip().lower()
        if st in ("paused", "burned"):
            continue
        blocked, reason = domain_is_send_blocked(conn, did)
        rem = domain_remaining_today(conn, d)
        d["_remaining_today"] = rem
        d["_sent_today"] = domain_sent_today(conn, did)
        d["_blocked"] = blocked
        d["_block_reason"] = reason
        if blocked or rem <= 0:
            continue
        out.append(d)
    return out


def pick_tenant_domain(
    conn,
    tenant_id: int | None,
    *,
    prefer_cohort: str | None = None,
    exclude_ids: set[int] | None = None,
) -> int | None:
    """En iyi domain: kalan slot ↓, sağlık ↓, warm_status, cohort tercihi."""
    pool = list_sendable_domains(conn, tenant_id, exclude_ids=exclude_ids)
    if not pool:
        return None
    prefer = (prefer_cohort or "").strip().lower() or None

    def score(d: dict) -> tuple:
        rem = int(d.get("_remaining_today") or 0)
        health = int(d.get("health_score") or 0)
        warm = WARM_RANK.get((d.get("warm_status") or "").strip().lower(), 0)
        cohort = (d.get("warmup_cohort") or "new").strip().lower()
        cohort_boost = 1 if prefer and cohort == prefer else 0
        # legacy genelde daha olgun — prefer yoksa hafif bonus
        if not prefer and cohort == "legacy":
            cohort_boost = 1
        return (rem, health, warm, cohort_boost, -int(d["id"]))

    pool.sort(key=score, reverse=True)
    return int(pool[0]["id"])


def tenant_domain_capacity_snapshot(conn, tenant_id: int | None) -> dict:
    allocated = _pool_domains(conn, tenant_id)
    sendable = []
    remaining_sum = 0
    domains = []
    for d in allocated:
        did = int(d["id"])
        sent = domain_sent_today(conn, did)
        rem = domain_remaining_today(conn, d)
        st = (d.get("warm_status") or "").strip().lower()
        blocked = st in ("paused", "burned") or rem <= 0
        from mail_domain_health import domain_is_send_blocked
        is_blocked, reason = domain_is_send_blocked(conn, did)
        blocked = blocked or is_blocked
        item = {
            "id": did,
            "domain": d.get("domain") or "",
            "warm_status": st,
            "warmup_cohort": (d.get("warmup_cohort") or "new"),
            "daily_cap": int(d.get("daily_cap") or 0),
            "sent_today": sent,
            "remaining_today": rem,
            "health_score": int(d.get("health_score") or 0),
            "sendable": not blocked and rem > 0,
            "block_reason": reason if is_blocked else ("cap" if rem <= 0 else ""),
        }
        domains.append(item)
        if item["sendable"]:
            sendable.append(item)
            remaining_sum += rem
    return {
        "allocated_count": len(allocated),
        "sendable_count": len(sendable),
        "remaining_today": remaining_sum,
        "domains": domains,
        "auto_default": True,
        "note": "Kampanya domain seçmez — sistem sağlık + günlük cap’e göre döner.",
    }


def campaign_is_auto(camp) -> bool:
    if not camp:
        return False
    if int(camp.get("auto_domain") or 0) == 1:
        return True
    # Eski kayıt: domain_id NULL → auto say
    return camp.get("domain_id") in (None, "", 0)
