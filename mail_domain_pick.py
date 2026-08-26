"""Tenant kampanyaları için otomatik domain seçimi / kapasite.

Firma domain seçmez — tahsisli, sağlıklı, günlük cap’i kalan domainler
arasında rotasyon. Isıtma programının yazdığı daily_cap yakıtıdır.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from database import execute, fetchall, fetchone, scalar

try:
    from zoneinfo import ZoneInfo
except Exception:  # pragma: no cover
    ZoneInfo = None  # type: ignore

_FALLBACK_TZ = timezone(timedelta(hours=3))  # Europe/Istanbul sabit offset yedeği


def _op_tz(conn=None):
    """Domain günlük cap penceresi artık Ayarlar'daki 'alibaba_daily_quota_tz' ile
    hizalı — eskiden burada sabit Europe/Istanbul kullanılıyordu, hesap bazlı Alibaba
    kotası (mail_account_quota) ise ayrı/yapılandırılabilir bir TZ kullanıyordu; bu
    ikisi arası uyumsuzluk "gün başlangıcı" saatini kaydırıp günlük sayaçların
    Alibaba'nın kendi günüyle örtüşmemesine yol açabiliyordu."""
    name = "Europe/Istanbul"
    if conn is not None:
        try:
            from mail_account_quota import get_quota_tz_name
            name = get_quota_tz_name(conn) or name
        except Exception:
            pass
    if ZoneInfo is not None:
        try:
            return ZoneInfo(name)
        except Exception:
            pass
    return _FALLBACK_TZ


WARM_RANK = {
    "warm": 3,
    "warming": 2,
    "cold": 1,
    "paused": 0,
    "burned": 0,
}


def day_since_iso_utc(conn=None) -> str:
    """Ayarlar'daki Alibaba kota TZ'sine göre gün başlangıcı → UTC ISO
    (domain_is_send_blocked ile aynı mantık/aynı TZ kaynağı)."""
    now_local = datetime.now(_op_tz(conn))
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
            conn.commit()
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass


def domain_sent_today(conn, domain_id: int) -> int:
    from mail_account_quota import send_stats_today
    return send_stats_today(conn, domain_id=int(domain_id))["used"]


def domain_remaining_today(conn, domain_row) -> int:
    """Kalan günlük slot. daily_cap<=0 → 0 (güvenli: sınırsız sayma)."""
    cap = int(domain_row.get("daily_cap") or 0)
    if cap <= 0:
        return 0
    sent = domain_sent_today(conn, int(domain_row["id"]))
    return max(0, cap - sent)


def _sent_today_by_domain(conn, domain_ids: list[int]) -> dict[int, int]:
    """Havuzdaki TÜM domainler için bugün kota yiyen gönderim (tek sorgu)."""
    from mail_account_quota import send_stats_today_by_domain
    stats = send_stats_today_by_domain(conn, domain_ids)
    return {int(i): int((stats.get(int(i)) or {}).get("used") or 0) for i in domain_ids}


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


FAIL_SKIP_PCT = 20.0
FAIL_SKIP_MIN = 40


def list_sendable_domains(
    conn,
    tenant_id: int | None,
    *,
    exclude_ids: set[int] | None = None,
) -> list[dict]:
    """paused/burned/cap-dolu / bugün Alibaba fail şişmiş hariç."""
    from mail_account_quota import send_stats_today_by_domain

    exclude_ids = exclude_ids or set()
    pool = [d for d in _pool_domains(conn, tenant_id) if int(d["id"]) not in exclude_ids]
    ids = [int(d["id"]) for d in pool]
    stats_by = send_stats_today_by_domain(conn, ids)

    out = []
    for d in pool:
        did = int(d["id"])
        st = (d.get("warm_status") or "").strip().lower()
        if st in ("paused", "burned"):
            continue
        cap = int(d.get("daily_cap") or 0)
        stt = stats_by.get(did) or {}
        sent = int(stt.get("used") or 0)
        fail = int(stt.get("fail") or 0)
        rem = max(0, cap - sent) if cap > 0 else 0
        d["_remaining_today"] = rem
        d["_sent_today"] = sent
        d["_fail_today"] = fail
        d["_blocked"] = False
        d["_block_reason"] = ""
        if rem <= 0:
            continue
        if sent >= FAIL_SKIP_MIN and (100.0 * fail / sent) >= FAIL_SKIP_PCT:
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
    from mail_account_quota import send_stats_today_by_domain
    from mail_tenant import domain_has_smtp, list_allocated_domains

    if tenant_id:
        allocated = [dict(r) for r in (list_allocated_domains(conn, int(tenant_id)) or [])]
    else:
        allocated = [dict(r) for r in (fetchall(conn, "SELECT * FROM mail_domains ORDER BY id ASC") or [])]
    ids = [int(d["id"]) for d in allocated]
    stats_by = send_stats_today_by_domain(conn, ids)
    sendable = []
    remaining_sum = 0
    sent_sum = 0
    ok_sum = 0
    fail_sum = 0
    queued_sum = 0
    total_cap = 0
    domains = []
    day_label = ""
    try:
        now_local = datetime.now(_op_tz(conn))
        day_label = now_local.strftime("%d.%m.%Y") + " TR"
    except Exception:
        day_label = "bugün"
    for d in allocated:
        did = int(d["id"])
        stt = stats_by.get(did) or {}
        sent = int(stt.get("used") or 0)
        ok = int(stt.get("success") or 0)
        fail = int(stt.get("fail") or 0)
        queued = int(stt.get("queued") or 0)
        cap = int(d.get("daily_cap") or 0)
        rem = max(0, cap - sent) if cap > 0 else 0
        st = (d.get("warm_status") or "").strip().lower()
        smtp_ok = domain_has_smtp(d)
        local = (d.get("from_local") or "noreply").strip() or "noreply"
        host = (d.get("domain") or "").strip()
        is_blocked = st in ("paused", "burned")
        fail_hot = sent >= 40 and (100.0 * fail / max(sent, 1)) >= 20.0
        if not smtp_ok:
            reason = "SMTP yok"
        elif is_blocked:
            reason = f"Domain {st}"
        elif rem <= 0:
            reason = "cap"
        elif fail_hot:
            reason = "bugün fail yüksek"
        else:
            reason = ""
        can_send = smtp_ok and not is_blocked and rem > 0 and not fail_hot
        pct = round(100.0 * sent / cap, 1) if cap > 0 else 0.0
        item = {
            "id": did,
            "domain": host,
            "from_local": local,
            "from_email": f"{local}@{host}" if host else local,
            "warm_status": st,
            "warmup_cohort": (d.get("warmup_cohort") or "new"),
            "daily_cap": cap,
            "sent_today": sent,
            "success_today": ok,
            "fail_today": fail,
            "queued_today": queued,
            "remaining_today": rem,
            "pct_used": min(100.0, max(0.0, pct)),
            "health_score": int(d.get("health_score") or 0),
            "smtp_ready": smtp_ok,
            "sendable": can_send,
            "block_reason": reason,
        }
        domains.append(item)
        sent_sum += sent
        ok_sum += ok
        fail_sum += fail
        queued_sum += queued
        if cap > 0 and smtp_ok:
            total_cap += cap
        if item["sendable"]:
            sendable.append(item)
            remaining_sum += rem
    return {
        "allocated_count": len(allocated),
        "sendable_count": len(sendable),
        "remaining_today": remaining_sum,
        "sent_today": sent_sum,
        "success_today": ok_sum,
        "fail_today": fail_sum,
        "queued_today": queued_sum,
        "total_cap": total_cap,
        "domains": domains,
        "day_label": day_label,
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
