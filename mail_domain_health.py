"""Domain sağlık metrikleri — bounce / fail / complaint spike → otomatik pause."""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timedelta, timezone

from database import execute, fetchall, fetchone, get_db, iso, scalar, utcnow

WINDOW_HOURS = 24
MIN_SAMPLE = 20
BOUNCE_RATE_MAX = 5.0
FAIL_RATE_MAX = 10.0
COMPLAINT_RATE_MAX = 0.3

try:
    from zoneinfo import ZoneInfo
    OP_TZ = ZoneInfo("Europe/Istanbul")
except Exception:
    OP_TZ = timezone(timedelta(hours=3))


def _domain_send_stats(conn, domain_id: int, *, hours: int = WINDOW_HOURS) -> dict:
    since = iso(utcnow() - timedelta(hours=max(1, int(hours))))
    rows = fetchall(
        conn,
        """
        SELECT status, LOWER(COALESCE(error,'')) AS err
        FROM mail_sends
        WHERE domain_id = ? AND created_at >= ?
        """,
        (int(domain_id), since),
    ) or []
    total = bounced = failed = complaints = 0
    for r in rows:
        st = (r["status"] or "").strip().lower()
        err = r["err"] or ""
        if st in ("sent", "simulated", "bounced", "failed"):
            total += 1
        if st == "bounced":
            bounced += 1
            if "complaint" in err:
                complaints += 1
        elif st == "failed":
            failed += 1
        if "complaint" in err and st != "bounced":
            complaints += 1
    return {
        "total": total,
        "bounced": bounced,
        "failed": failed,
        "complaints": complaints,
        "since": since,
    }


def compute_rates(stats: dict) -> dict:
    total = max(int(stats.get("total") or 0), 0)
    bounced = int(stats.get("bounced") or 0)
    failed = int(stats.get("failed") or 0)
    complaints = int(stats.get("complaints") or 0)
    denom = total or 1
    return {
        **stats,
        "bounce_rate": round(100.0 * bounced / denom, 2) if total else 0.0,
        "fail_rate": round(100.0 * failed / denom, 2) if total else 0.0,
        "complaint_rate": round(100.0 * complaints / denom, 3) if total else 0.0,
        "sample_ok": total >= MIN_SAMPLE,
    }


def should_pause(rates: dict) -> tuple[bool, str]:
    if not rates.get("sample_ok"):
        return False, ""
    if rates["bounce_rate"] > BOUNCE_RATE_MAX:
        return True, f"bounce_rate={rates['bounce_rate']}% > {BOUNCE_RATE_MAX}% (n={rates['total']})"
    if rates["fail_rate"] > FAIL_RATE_MAX:
        return True, f"fail_rate={rates['fail_rate']}% > {FAIL_RATE_MAX}% (n={rates['total']})"
    if rates["complaint_rate"] > COMPLAINT_RATE_MAX:
        return True, f"complaint_rate={rates['complaint_rate']}% > {COMPLAINT_RATE_MAX}% (n={rates['total']})"
    return False, ""


def pause_domain(conn, domain_id: int, reason: str) -> bool:
    row = fetchone(
        conn,
        "SELECT id, domain, warm_status FROM mail_domains WHERE id = ?",
        (int(domain_id),),
    )
    if not row:
        return False
    st = (row.get("warm_status") or "").strip().lower()
    if st in ("paused", "burned"):
        return False
    now = iso(utcnow())
    execute(
        conn,
        """
        UPDATE mail_domains
        SET warm_status = 'paused',
            health_score = CASE
                WHEN COALESCE(health_score, 100) > 20 THEN 20
                ELSE COALESCE(health_score, 20)
            END
        WHERE id = ?
        """,
        (int(domain_id),),
    )
    try:
        # Otomatik domain kampanyaları tek domain pause’ta durmaz — worker başka domain’e döner
        try:
            from mail_domain_pick import ensure_auto_domain_column
            ensure_auto_domain_column(conn)
        except Exception:
            pass
        execute(
            conn,
            """
            UPDATE mail_campaigns
            SET status = 'paused', updated_at = ?, error = ?
            WHERE domain_id = ?
              AND status IN ('queued', 'sending', 'scheduled')
              AND COALESCE(auto_domain, 0) = 0
            """,
            (now, f"Domain auto-pause: {reason}"[:400], int(domain_id)),
        )
    except Exception as exc:
        print(f"⚠️  pause campaigns for domain {domain_id}: {exc}")
        try:
            from database import safe_rollback
            safe_rollback(conn)
        except Exception:
            pass
    print(f"✉️  AUTO-PAUSE domain #{domain_id} ({row.get('domain')}): {reason}")
    return True


def evaluate_and_maybe_pause(conn, domain_id: int, *, hours: int = WINDOW_HOURS) -> dict:
    stats = _domain_send_stats(conn, domain_id, hours=hours)
    rates = compute_rates(stats)
    pause, reason = should_pause(rates)
    paused = False
    if pause:
        paused = pause_domain(conn, domain_id, reason)
    return {**rates, "should_pause": pause, "paused": paused, "reason": reason}


def review_all_active_domains(conn) -> list[dict]:
    rows = fetchall(
        conn,
        """
        SELECT id, domain, warm_status FROM mail_domains
        WHERE LOWER(COALESCE(warm_status, 'cold')) NOT IN ('paused', 'burned')
        ORDER BY id ASC
        LIMIT 100
        """,
    ) or []
    out = []
    for r in rows:
        try:
            result = evaluate_and_maybe_pause(conn, int(r["id"]))
            result["domain_id"] = int(r["id"])
            result["domain"] = r.get("domain")
            out.append(result)
        except Exception as exc:
            print(f"⚠️  domain health #{r.get('id')}: {exc}")
            try:
                from database import safe_rollback
                safe_rollback(conn)
            except Exception:
                pass
    return out


def domain_is_send_blocked(conn, domain_id) -> tuple[bool, str]:
    if not domain_id:
        return False, ""
    row = fetchone(
        conn,
        "SELECT id, domain, warm_status, daily_cap FROM mail_domains WHERE id = ?",
        (int(domain_id),),
    )
    if not row:
        return True, "Domain bulunamadı"
    st = (row.get("warm_status") or "").strip().lower()
    if st in ("paused", "burned"):
        return True, f"Domain {st}"
    daily_cap = int(row.get("daily_cap") or 0)
    if daily_cap > 0:
        now_local = datetime.now(OP_TZ)
        day_start = now_local.replace(hour=0, minute=0, second=0, microsecond=0)
        since = day_start.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        sent_today = int(
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
        if sent_today >= daily_cap:
            return True, f"daily_cap doldu ({sent_today}/{daily_cap})"
    return False, ""


def tick_domain_health_once() -> int:
    paused_n = 0
    try:
        with closing(get_db()) as conn:
            results = review_all_active_domains(conn)
            conn.commit()
            paused_n = sum(1 for r in results if r.get("paused"))
    except Exception as exc:
        print(f"⚠️  tick_domain_health: {exc}")
    return paused_n
