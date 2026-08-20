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


def _sent_today_by_domain(conn, domain_ids: list[int]) -> dict[int, int]:
    """Havuzdaki TÜM domainler için 'bugün gönderilen' sayısını TEK sorguda getirir.

    Öncesinde her domain için ayrı ayrı COUNT(*) sorgusu atılıyordu (N+1) —
    ~50 domainlik havuzda tek bir pick_tenant_domain çağrısı 50-100+ sorgu
    üretebiliyordu; kampanya worker'ı bunu recipient/batch başına tekrar tekrar
    çağırdığı için toplam sorgu sayısı hızla büyüyordu.
    """
    ids = [int(i) for i in domain_ids]
    if not ids:
        return {}
    since = day_since_iso_utc()
    ph = ",".join(["?"] * len(ids))
    rows = fetchall(
        conn,
        f"""
        SELECT domain_id, COUNT(*) AS cnt
        FROM mail_sends
        WHERE domain_id IN ({ph})
          AND status IN ('sent', 'simulated')
          AND created_at >= ?
        GROUP BY domain_id
        """,
        tuple(ids) + (since,),
    ) or []
    out = {int(i): 0 for i in ids}
    for r in rows:
        try:
            out[int(r["domain_id"])] = int(r["cnt"] or 0)
        except Exception:
            continue
    return out


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
    exclude_ids = exclude_ids or set()
    pool = [d for d in _pool_domains(conn, tenant_id) if int(d["id"]) not in exclude_ids]
    sent_by_domain = _sent_today_by_domain(conn, [int(d["id"]) for d in pool])

    out = []
    for d in pool:
        did = int(d["id"])
        st = (d.get("warm_status") or "").strip().lower()
        if st in ("paused", "burned"):
            continue
        cap = int(d.get("daily_cap") or 0)
        sent = sent_by_domain.get(did, 0)
        rem = max(0, cap - sent) if cap > 0 else 0
        d["_remaining_today"] = rem
        d["_sent_today"] = sent
        d["_blocked"] = False
        d["_block_reason"] = ""
        if rem <= 0:
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
    sent_by_domain = _sent_today_by_domain(conn, [int(d["id"]) for d in allocated])
    sendable = []
    remaining_sum = 0
    domains = []
    for d in allocated:
        did = int(d["id"])
        sent = sent_by_domain.get(did, 0)
        cap = int(d.get("daily_cap") or 0)
        rem = max(0, cap - sent) if cap > 0 else 0
        st = (d.get("warm_status") or "").strip().lower()
        is_blocked = st in ("paused", "burned")
        reason = f"Domain {st}" if is_blocked else ("cap" if rem <= 0 else "")
        blocked = is_blocked or rem <= 0
        item = {
            "id": did,
            "domain": d.get("domain") or "",
            "warm_status": st,
            "warmup_cohort": (d.get("warmup_cohort") or "new"),
            "daily_cap": cap,
            "sent_today": sent,
            "remaining_today": rem,
            "health_score": int(d.get("health_score") or 0),
            "sendable": not blocked,
            "block_reason": reason,
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
