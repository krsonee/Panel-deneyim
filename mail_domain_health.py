"""Domain sağlık metrikleri — bounce / fail / complaint spike → otomatik pause."""

from __future__ import annotations

from contextlib import closing
from datetime import datetime, timedelta, timezone

from database import execute, fetchall, fetchone, get_db, iso, row_get, scalar, utcnow

WINDOW_HOURS = 24
MIN_SAMPLE = 20
# Alibaba hesap yöneticisi hesap genelinde ≥%90 başarı istiyor (limit artırım şartı,
# ≥%80 sürdürme şartı). Domain eşiklerini bu hedeften ÖNCE alarm verecek şekilde
# sıkılaştırdık — eskiden %10 fail'e kadar izin veriyordu, bu tek başına hesabı
# %90'ın altına düşürebiliyordu.
BOUNCE_RATE_MAX = 6.0
# SMTP fail neredeyse 0 kalıyordu; asıl kırmızı Alibaba real_status=failed (Gmail 4.7.28).
# n≥80 iken %22 üstü = çürük (vipileti %78 / 2624).
# 27.08: yeni domainler n=22–31 ve %22.2 ile kıl payı pause oldu (Gmail geçici 4.7.28).
# Küçük örnekte ancak %45+ (alkanka %100) durdurur.
FAIL_RATE_MAX = 22.0
FAIL_PAUSE_FULL_N = 80
FAIL_RATE_MAX_SMALL_N = 45.0
COMPLAINT_RATE_MAX = 0.3
# Kısıtlı hesap: yeni cohort ısınırken günlük tavan; legacy ısınırken WARMING_HARD_MAX.
NEW_COHORT_DAILY_CAP = 40

try:
    from zoneinfo import ZoneInfo
    OP_TZ = ZoneInfo("Europe/Istanbul")
except Exception:
    OP_TZ = timezone(timedelta(hours=3))


def _daily_cap_tz(conn):
    """daily_cap günlük penceresi Ayarlar'daki 'alibaba_daily_quota_tz' ile hizalı —
    eskiden burada sabit Europe/Istanbul kullanılıyordu, hesap bazlı Alibaba kotası
    (mail_account_quota) ayrı/yapılandırılabilir bir TZ kullanıyordu; bu ikisi arası
    uyumsuzluk domain günlük sayaçlarının Alibaba'nın kendi günüyle örtüşmemesine
    yol açabiliyordu (bkz mail_domain_pick._op_tz — aynı mantık)."""
    try:
        from mail_domain_pick import _op_tz
        return _op_tz(conn)
    except Exception:
        return OP_TZ


def _domain_send_stats(conn, domain_id: int, *, hours: int = WINDOW_HOURS) -> dict:
    since = iso(utcnow() - timedelta(hours=max(1, int(hours))))
    try:
        rows = fetchall(
            conn,
            """
            SELECT
              LOWER(COALESCE(status, '')) AS st,
              LOWER(COALESCE(error, '')) AS err,
              LOWER(COALESCE(real_status, '')) AS real_st
            FROM mail_sends
            WHERE domain_id = ? AND created_at >= ?
            """,
            (int(domain_id), since),
        ) or []
    except Exception:
        try:
            from database import safe_rollback
            safe_rollback(conn)
        except Exception:
            pass
        rows = fetchall(
            conn,
            """
            SELECT status AS st, LOWER(COALESCE(error,'')) AS err, '' AS real_st
            FROM mail_sends
            WHERE domain_id = ? AND created_at >= ?
            """,
            (int(domain_id), since),
        ) or []
    total = bounced = failed = complaints = 0
    for r in rows:
        st = (row_get(r, "st") or "").strip().lower()
        err = row_get(r, "err") or ""
        real_st = (row_get(r, "real_st") or "").strip().lower()
        if st not in ("sent", "simulated", "bounced", "failed"):
            continue
        total += 1
        # Alibaba gerçek sonuç (status çoğu zaman 'sent' kalır) — 26.08 Gmail 4.7.28
        if real_st in ("failed", "spam"):
            failed += 1
        elif real_st == "invalid":
            bounced += 1
        elif st == "bounced":
            bounced += 1
        elif st == "failed":
            failed += 1
        if "complaint" in err:
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
    n = int(rates.get("total") or 0)
    if rates["bounce_rate"] > BOUNCE_RATE_MAX:
        return True, f"bounce_rate={rates['bounce_rate']}% > {BOUNCE_RATE_MAX}% (n={n})"
    fail = float(rates["fail_rate"] or 0)
    if n < FAIL_PAUSE_FULL_N:
        if fail > FAIL_RATE_MAX_SMALL_N:
            return True, (
                f"fail_rate={fail}% > {FAIL_RATE_MAX_SMALL_N}% "
                f"(n={n} < {FAIL_PAUSE_FULL_N})"
            )
    elif fail > FAIL_RATE_MAX:
        return True, f"fail_rate={fail}% > {FAIL_RATE_MAX}% (n={n})"
    if rates["complaint_rate"] > COMPLAINT_RATE_MAX:
        return True, f"complaint_rate={rates['complaint_rate']}% > {COMPLAINT_RATE_MAX}% (n={n})"
    return False, ""


def pause_domain(conn, domain_id: int, reason: str) -> bool:
    row = fetchone(
        conn,
        "SELECT id, domain, warm_status FROM mail_domains WHERE id = ?",
        (int(domain_id),),
    )
    if not row:
        return False
    st = (row_get(row, "warm_status") or "").strip().lower()
    if st in ("paused", "burned"):
        return False
    now = iso(utcnow())
    note = f"{now} — otomatik pause: {reason}"[:500]
    execute(
        conn,
        """
        UPDATE mail_domains
        SET warm_status = 'paused',
            health_score = CASE
                WHEN COALESCE(health_score, 100) > 20 THEN 20
                ELSE COALESCE(health_score, 20)
            END,
            health_note = ?
        WHERE id = ?
        """,
        (note, int(domain_id)),
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
    print(f"✉️  AUTO-PAUSE domain #{domain_id} ({row_get(row, 'domain')}): {reason}")
    return True


def unpause_domain(conn, domain_id: int) -> bool:
    """Manuel superadmin aksiyonu — auto-pause'u geri alır.

    health_score önceden hiçbir yerde 100'e geri yazılmıyordu (bkz. pause_domain);
    bir domain gerçek sorunu çözüldükten sonra bile sürekli 'paused' + health=20
    kalıyordu ve panelde geri alacak bir buton yoktu. Bu, warm_day'i (kaldığı
    yerden devam) ve daily_cap/hourly_cap'i KORUR — sadece durumu ve sağlığı
    sıfırlar; gerçek sorun düzelmediyse health tekrar düşüp yeniden pause olur.
    """
    row = fetchone(conn, "SELECT id, warm_status FROM mail_domains WHERE id = ?", (int(domain_id),))
    if not row:
        return False
    st = (row_get(row, "warm_status") or "").strip().lower()
    if st not in ("paused", "burned"):
        return False
    execute(
        conn,
        """
        UPDATE mail_domains
        SET warm_status = 'warming', health_score = 100, health_note = ''
        WHERE id = ?
        """,
        (int(domain_id),),
    )
    return True


def evaluate_and_maybe_pause(conn, domain_id: int, *, hours: int = WINDOW_HOURS) -> dict:
    stats = _domain_send_stats(conn, domain_id, hours=hours)
    rates = compute_rates(stats)
    pause, reason = should_pause(rates)
    paused = False
    if pause:
        paused = pause_domain(conn, domain_id, reason)
    return {**rates, "should_pause": pause, "paused": paused, "reason": reason}


def enforce_constrained_caps(conn) -> int:
    """Yeni cohort ısınma tavanı 40; ısınan her domain ≤ 600. paused cap'e dokunma."""
    n = 0
    try:
        from mail_warmup_program import WARMING_HARD_MAX
        rows = fetchall(
            conn,
            """
            SELECT id, daily_cap, hourly_cap,
                   LOWER(COALESCE(warm_status, 'cold')) AS st,
                   COALESCE(NULLIF(warmup_cohort, ''), 'new') AS cohort
            FROM mail_domains
            """,
        ) or []
        for r in rows:
            st = (row_get(r, "st") or "").strip().lower()
            if st in ("paused", "burned"):
                continue
            cap = int(row_get(r, "daily_cap") or 0)
            hourly = int(row_get(r, "hourly_cap") or 0)
            cohort = (row_get(r, "cohort") or "new").strip().lower()
            new_cap = cap
            new_hour = hourly
            if cohort == "new" and st != "warm":
                if cap <= 0 or cap > NEW_COHORT_DAILY_CAP:
                    new_cap = NEW_COHORT_DAILY_CAP
                new_hour = max(4, min(12, new_hour if new_hour > 0 else 8))
            elif st == "warming" and cap > WARMING_HARD_MAX:
                new_cap = WARMING_HARD_MAX
                new_hour = min(hourly if hourly > 0 else 40, 40)
            if new_cap != cap or new_hour != hourly:
                execute(
                    conn,
                    "UPDATE mail_domains SET daily_cap = ?, hourly_cap = ? WHERE id = ?",
                    (int(new_cap), int(new_hour), int(r["id"])),
                )
                n += 1
    except Exception as exc:
        print(f"⚠️  enforce_constrained_caps: {exc}")
    return n


def review_paused_domains_maybe_unpause(conn) -> list[dict]:
    """Yeni eşikle artık durmaması gereken kıl-payı pause'ları geri aç.

    vipileti (%78 / 2624) ve alkanka (%100 / 20) should_pause True kalır.
    """
    rows = fetchall(
        conn,
        """
        SELECT id, domain FROM mail_domains
        WHERE LOWER(COALESCE(warm_status, '')) = 'paused'
        ORDER BY id ASC
        LIMIT 200
        """,
    ) or []
    out = []
    for r in rows:
        did = int(r["id"])
        try:
            stats = _domain_send_stats(conn, did, hours=WINDOW_HOURS)
            rates = compute_rates(stats)
            pause, reason = should_pause(rates)
            if pause:
                out.append({**rates, "domain_id": did, "domain": row_get(r, "domain"), "unpaused": False})
                continue
            ok = unpause_domain(conn, did)
            if ok:
                print(
                    f"✉️  AUTO-UNPAUSE domain #{did} ({row_get(r, 'domain')}): "
                    f"fail={rates.get('fail_rate')}% n={rates.get('total')} — yeni eşik"
                )
            out.append({
                **rates,
                "domain_id": did,
                "domain": row_get(r, "domain"),
                "unpaused": bool(ok),
                "reason": reason,
            })
        except Exception as exc:
            print(f"⚠️  domain unpause-check #{row_get(r, 'id')}: {exc}")
            try:
                from database import safe_rollback
                safe_rollback(conn)
            except Exception:
                pass
    return out


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
            result["domain"] = row_get(r, "domain")
            out.append(result)
        except Exception as exc:
            print(f"⚠️  domain health #{row_get(r, 'id')}: {exc}")
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
    st = (row_get(row, "warm_status") or "").strip().lower()
    if st in ("paused", "burned"):
        return True, f"Domain {st}"
    daily_cap = int(row_get(row, "daily_cap") or 0)
    if daily_cap > 0:
        try:
            from mail_domain_pick import domain_sent_today
            sent_today = domain_sent_today(conn, int(domain_id))
        except Exception:
            sent_today = 0
        if sent_today >= daily_cap:
            return True, f"daily_cap doldu ({sent_today}/{daily_cap})"
    try:
        from mail_account_quota import send_stats_today
        stt = send_stats_today(conn, domain_id=int(domain_id))
        used = int(stt.get("used") or 0)
        fail = int(stt.get("fail") or 0)
        if used >= 40 and (100.0 * fail / used) >= 20.0:
            return True, f"bugün Alibaba fail %{round(100.0 * fail / used, 1)} (n={used}) — domain dinleniyor"
    except Exception:
        pass
    return False, ""


def tick_domain_health_once() -> int:
    paused_n = 0
    unpaused_n = 0
    try:
        with closing(get_db()) as conn:
            try:
                unpaused_n = sum(
                    1 for r in review_paused_domains_maybe_unpause(conn) if r.get("unpaused")
                )
            except Exception as uexc:
                print(f"⚠️  paused unpause pass: {uexc}")
                try:
                    from database import safe_rollback
                    safe_rollback(conn)
                except Exception:
                    pass
            if unpaused_n:
                print(f"✉️  domain auto-unpause count={unpaused_n}")
            conn.commit()
            try:
                n_cap = enforce_constrained_caps(conn)
                if n_cap:
                    print(f"✉️  constrained caps updated={n_cap}")
            except Exception as cexc:
                print(f"⚠️  constrained caps: {cexc}")
            results = review_all_active_domains(conn)
            conn.commit()
            paused_n = sum(1 for r in results if r.get("paused"))
    except Exception as exc:
        print(f"⚠️  tick_domain_health: {exc}")
    return paused_n
