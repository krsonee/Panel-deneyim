"""Mikromail — Pazar günü haftalık genel bakım (Europe/Istanbul).

State: mail_settings.weekly_maintenance_v1 (JSON)
- Operatör checklist (manuel tik)
- Otomatik: son gönderime hizalama + domain cap sync
Deploy/startup’ta Pazar ise haftada 1 kez auto-run.
Force run herhangi bir günde çalışır.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore

from database import (
    get_mail_setting,
    upsert_mail_setting,
)

SETTING_KEY = "weekly_maintenance_v1"
OP_TZ = ZoneInfo("Europe/Istanbul") if ZoneInfo else timezone.utc

# Operatör checklist — Pazar bakım rutini
WEEKLY_TASKS = [
    {
        "key": "cap_sync",
        "title": "Domain cap senkron",
        "hint": "Isıtma gününe göre daily_cap’leri güncelle; status warming kalsın.",
        "auto": True,
    },
    {
        "key": "warmup_catchup",
        "title": "Isıtma catch-up (son gönderim)",
        "hint": "Pasif/hasta günlerinden sonra programı son gerçek mail gününe hizala; cap şişmesin.",
        "auto": True,
    },
    {
        "key": "list_hygiene",
        "title": "Liste hijyeni",
        "hint": "Yeni kontaklara scrub; mail_invalid birikimini sil / suppression’da tut.",
        "auto": False,
    },
    {
        "key": "spam_probe",
        "title": "Spam probe (test mail)",
        "hint": "Her aktif domainden 1–2 test → kendi Gmail/Outlook. Spam’deyse Spam değil.",
        "auto": False,
    },
    {
        "key": "bounce_review",
        "title": "Bounce / fail gözden geçirme",
        "hint": "Son 7 gün bounce > %5 veya fail spike → o domaini pause.",
        "auto": False,
    },
    {
        "key": "template_rotation",
        "title": "Şablon rotasyonu",
        "hint": "Aynı HTML’i 5 domainde peş peşe basma; Bizzo/Makro şablonlarını çevir.",
        "auto": False,
    },
]


def _now() -> datetime:
    return datetime.now(OP_TZ)


def _today() -> date:
    return _now().date()


def _today_str() -> str:
    return _today().isoformat()


def is_sunday(d: date | None = None) -> bool:
    d = d or _today()
    return d.weekday() == 6  # Mon=0 … Sun=6


def sunday_week_key(d: date | None = None) -> str:
    """Haftayı o haftanın Pazar günü ISO tarihi ile kimliklendir."""
    d = d or _today()
    # Bu haftanın Pazarı: geriye doğru Sunday’e git
    offset = (d.weekday() + 1) % 7
    sunday = d - timedelta(days=offset)
    return sunday.isoformat()


def default_state() -> dict:
    return {
        "version": 1,
        "schedule": "sunday",  # sabit: her Pazar
        "timezone": "Europe/Istanbul",
        "completions": {},  # week_key -> { task_key: true }
        "runs": {},  # week_key -> { ran_at, actions: [...] }
        "last_run_week": None,
        "last_run_at": None,
        "notes": "",
    }


def load_state(conn) -> dict:
    raw = get_mail_setting(conn, SETTING_KEY, "") or ""
    st = default_state()
    if not raw.strip():
        return st
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            st.update(data)
    except Exception:
        pass
    if not isinstance(st.get("completions"), dict):
        st["completions"] = {}
    if not isinstance(st.get("runs"), dict):
        st["runs"] = {}
    return st


def save_state(conn, state: dict) -> None:
    upsert_mail_setting(conn, SETTING_KEY, json.dumps(state, ensure_ascii=False))


def _warmup_gap_days(conn) -> int:
    """Son gerçek bulk gönderimden bu yana gün."""
    try:
        from mail_warmup_program import activity_gap_days
        return int(activity_gap_days(conn) or 0)
    except Exception:
        return 0


def _sync_domain_caps(conn, *, soft: bool = False) -> dict:
    """Isıtma programı domainlerinin daily_cap’ini plana çek.

    soft=True (haftalık bakım / pasif dönüş): son gönderim gününe hizala,
    takvim gününe göre şişmiş cap’i geri al. Eski soft_day=4/5 hack’i kaldırıldı.
    """
    from mail_warmup_program import (
        activity_gap_days,
        compute_day_number,
        day_plan,
        load_state as wu_load,
        realign_to_last_send,
        save_state as wu_save,
        sync_program_caps,
    )

    wu = wu_load(conn)
    gap = activity_gap_days(conn, wu)
    day_n = compute_day_number(wu)
    note = ""
    realign_result = None
    effective_day = day_n

    if soft and wu.get("started_on") and (wu.get("domain_ids") or []):
        # Gap olsun olmasın bakımda son gönderime kilitle (takvim şişmesini düzelt)
        try:
            realign_result = realign_to_last_send(conn, advance=False)
            effective_day = int(realign_result.get("resume_day") or day_n)
            note = realign_result.get("note") or (
                f"son gönderime hizalandı → day {effective_day} (gap {gap}g)"
            )
            wu = wu_load(conn)
        except Exception as exc:
            note = f"realign atlandı: {exc}"
            print(f"⚠️  weekly realign: {exc}")

    sync = sync_program_caps(conn, wu, force=True)
    plan = day_plan(compute_day_number(wu_load(conn)))
    cap = int(sync.get("daily_cap") or plan["daily_cap_suggest"])

    # Program duraklatılmışsa bakımda soft resume
    resumed = False
    wu = wu_load(conn)
    if (wu.get("domain_ids") or []) and not wu.get("active") and wu.get("started_on"):
        wu["active"] = True
        wu_save(conn, wu)
        resumed = True
        try:
            sync_program_caps(conn, wu, force=True)
        except Exception:
            pass

    return {
        "domains_updated": int(sync.get("updated") or 0),
        "daily_cap": cap,
        "effective_day": effective_day,
        "calendar_day": day_n,
        "gap_days": gap,
        "soft_note": note,
        "resumed": resumed,
        "realign": realign_result,
        "last_send_date": (realign_result or {}).get("last_send_date"),
    }


def run_weekly_maintenance(conn, *, force: bool = False) -> dict:
    """Otomatik bakım adımlarını çalıştır; haftalık run kaydı yaz."""
    today = _today()
    week = sunday_week_key(today)
    st = load_state(conn)
    already = st.get("last_run_week") == week and bool((st.get("runs") or {}).get(week))
    if already and not force:
        return {
            "ok": True,
            "skipped": True,
            "reason": "Bu Pazar haftası bakım zaten çalıştı — tekrar için force=true",
            "week_key": week,
            "snapshot": snapshot(conn),
        }

    actions = []
    # 1) Son anlamlı bulk’a hizala + soft gap rollback + cap/hourly sync
    sync = _sync_domain_caps(conn, soft=True)
    actions.append({"action": "cap_sync", "result": sync})
    actions.append({"action": "warmup_catchup", "result": {
        "gap_days": sync.get("gap_days"),
        "effective_day": sync.get("effective_day"),
        "resumed": sync.get("resumed"),
        "last_send_date": sync.get("last_send_date"),
        "note": sync.get("soft_note") or "ok",
        "realign": sync.get("realign"),
    }})

    # 2) Domain sağlık taraması (bounce/fail spike → pause)
    health_rows = []
    try:
        from mail_domain_health import review_all_active_domains
        health_rows = review_all_active_domains(conn) or []
        actions.append({
            "action": "domain_health",
            "result": {
                "reviewed": len(health_rows),
                "paused": [r for r in health_rows if r.get("paused")],
                "samples": [
                    {
                        "domain": r.get("domain"),
                        "total": r.get("total"),
                        "bounce_rate": r.get("bounce_rate"),
                        "fail_rate": r.get("fail_rate"),
                        "should_pause": r.get("should_pause"),
                    }
                    for r in health_rows[:8]
                ],
            },
        })
    except Exception as exc:
        actions.append({"action": "domain_health", "result": {"ok": False, "error": str(exc)}})
        print(f"⚠️  weekly domain health: {exc}")

    # Auto task’leri bu hafta tamamlandı say
    comps = st.setdefault("completions", {})
    week_map = comps.setdefault(week, {})
    for t in WEEKLY_TASKS:
        if t.get("auto"):
            week_map[t["key"]] = True
    # Bounce review: tarama yapıldıysa operatör tik’i de kapat
    if health_rows is not None:
        week_map["bounce_review"] = True

    st["runs"][week] = {
        "ran_at": _now().isoformat(),
        "actions": actions,
        "forced": bool(force),
    }
    st["last_run_week"] = week
    st["last_run_at"] = _now().isoformat()
    save_state(conn, st)
    try:
        conn.commit()
    except Exception:
        pass
    return {
        "ok": True,
        "skipped": False,
        "week_key": week,
        "is_sunday": is_sunday(today),
        "actions": actions,
        "snapshot": snapshot(conn),
    }


def ensure_sunday_maintenance(conn) -> dict | None:
    """Startup: Pazar ise haftalık bakım; değilse gap ≥ 2 ise catch-up realign."""
    try:
        if is_sunday():
            return run_weekly_maintenance(conn, force=False)
    except Exception as exc:
        print(f"⚠️  weekly maintenance: {exc}")
        return {"ok": False, "error": str(exc)}

    # Hafta içi: hasta/pasif gap varsa hizala (Pazar bekleme)
    try:
        from mail_warmup_program import activity_gap_days, maybe_auto_realign_after_gap

        gap = activity_gap_days(conn)
        if gap >= 2:
            result = maybe_auto_realign_after_gap(conn)
            if result:
                try:
                    conn.commit()
                except Exception:
                    pass
                return {"ok": True, "weekday_catchup": True, "gap_days": gap, "result": result}
    except Exception as exc:
        print(f"⚠️  weekday warmup catchup: {exc}")
    return None


def set_weekly_task(conn, task_key: str, done: bool) -> dict:
    keys = {t["key"] for t in WEEKLY_TASKS}
    if task_key not in keys:
        raise ValueError("Bilinmeyen haftalık görev.")
    week = sunday_week_key()
    st = load_state(conn)
    comps = st.setdefault("completions", {})
    week_map = comps.setdefault(week, {})
    week_map[task_key] = bool(done)
    save_state(conn, st)
    try:
        conn.commit()
    except Exception:
        pass
    return snapshot(conn)


def snapshot(conn) -> dict:
    today = _today()
    week = sunday_week_key(today)
    st = load_state(conn)
    done_map = (st.get("completions") or {}).get(week) or {}
    tasks = []
    pending = 0
    for t in WEEKLY_TASKS:
        done = bool(done_map.get(t["key"]))
        if not done:
            pending += 1
        tasks.append({**t, "done": done})
    run = (st.get("runs") or {}).get(week)
    gap = _warmup_gap_days(conn)
    sunday = is_sunday(today)
    # Banner: Pazar bekleyen iş VEYA uzun gap (hafta içi catch-up hatırlatması)
    show_banner = (sunday and pending > 0) or (gap >= 2 and pending > 0)
    return {
        "today": today.isoformat(),
        "week_key": week,
        "is_sunday": sunday,
        "schedule": "Her Pazar (Europe/Istanbul) · gap≥2 günde otomatik catch-up",
        "tasks": tasks,
        "pending": pending,
        "all_done": pending == 0,
        "last_run_at": st.get("last_run_at"),
        "last_run_week": st.get("last_run_week"),
        "this_week_run": run,
        "warmup_gap_days": gap,
        "banner": {
            "show": show_banner,
            "text": (
                f"Pazar bakımı: {pending} görev bekliyor"
                if sunday
                else f"Haftalık bakım: {pending} görev · ısıtma gap {gap}g — «Bakımı çalıştır»"
            )
            + (f" · ısıtma gap {gap}g" if sunday and gap >= 2 else ""),
        },
        "notes": st.get("notes") or "",
    }
