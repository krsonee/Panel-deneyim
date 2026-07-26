"""Mikromail — Pazar günü haftalık genel bakım (Europe/Istanbul).

State: mail_settings.weekly_maintenance_v1 (JSON)
- Operatör checklist (manuel tik)
- Otomatik: domain cap sync, ısıtma soft-resume (pasiften sonra)
Deploy/startup’ta Pazar ise haftada 1 kez auto-run.
"""

from __future__ import annotations

import json
from datetime import date, datetime, timedelta, timezone

try:
    from zoneinfo import ZoneInfo
except ImportError:  # pragma: no cover
    ZoneInfo = None  # type: ignore

from database import (
    execute,
    fetchall,
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
        "title": "Isıtma catch-up",
        "hint": "Pasiften sonra programı yumuşak devam ettir; hacmi birden patlatma.",
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
    """Son ısıtma görevi / run’dan bu yana gün (yoksa started_on’a göre)."""
    try:
        from mail_warmup_program import load_state as wu_load, _today_str as wu_today
    except Exception:
        return 0
    st = wu_load(conn)
    today = date.fromisoformat(wu_today())
    # En son completion tarihi
    last = None
    for day_s in (st.get("completions") or {}):
        try:
            dd = date.fromisoformat(str(day_s)[:10])
        except Exception:
            continue
        if last is None or dd > last:
            last = dd
    if last is None and st.get("started_on"):
        try:
            last = date.fromisoformat(str(st["started_on"])[:10])
        except Exception:
            last = None
    if last is None:
        return 0
    return max(0, (today - last).days)


def _sync_domain_caps(conn, *, soft: bool = False) -> dict:
    """Isıtma programı domainlerinin daily_cap’ini plana çek."""
    from mail_warmup_program import (
        compute_day_number,
        day_plan,
        load_state as wu_load,
        save_state as wu_save,
    )

    wu = wu_load(conn)
    day_n = compute_day_number(wu)
    gap = _warmup_gap_days(conn)
    effective_day = day_n
    note = ""
    if soft or gap >= 2:
        # Pasiften sonra hacmi yumuşat — erken banda geri çek
        soft_day = min(day_n, 4 if gap >= 4 else 5)
        if soft_day < day_n:
            effective_day = soft_day
            wu["day_override"] = soft_day
            note = f"pasif gap={gap}g → soft day {soft_day} (takvim günü {day_n})"
            wu_save(conn, wu)
    plan = day_plan(effective_day)
    cap = int(plan["daily_cap_suggest"])
    updated = 0
    ids = wu.get("domain_ids") or []
    for did in ids:
        try:
            execute(
                conn,
                """
                UPDATE mail_domains
                SET daily_cap = ?,
                    warm_day = ?,
                    warm_status = CASE
                        WHEN warm_status IN ('burned', 'paused') THEN warm_status
                        WHEN ? >= 30 THEN 'warm'
                        ELSE 'warming'
                    END
                WHERE id = ?
                """,
                (cap, int(effective_day), int(effective_day), int(did)),
            )
            updated += 1
        except Exception:
            continue
    # Program duraklatılmışsa Pazar bakımında soft resume
    resumed = False
    if ids and not wu.get("active") and wu.get("started_on"):
        wu["active"] = True
        wu_save(conn, wu)
        resumed = True
    return {
        "domains_updated": updated,
        "daily_cap": cap,
        "effective_day": effective_day,
        "calendar_day": day_n,
        "gap_days": gap,
        "soft_note": note,
        "resumed": resumed,
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
            "reason": "Bu Pazar haftası bakım zaten çalıştı",
            "week_key": week,
            "snapshot": snapshot(conn),
        }

    actions = []
    # 1) Cap sync + catch-up
    sync = _sync_domain_caps(conn, soft=True)
    actions.append({"action": "cap_sync", "result": sync})
    actions.append({"action": "warmup_catchup", "result": {
        "gap_days": sync.get("gap_days"),
        "effective_day": sync.get("effective_day"),
        "resumed": sync.get("resumed"),
        "note": sync.get("soft_note") or "ok",
    }})

    # Auto task’leri bu hafta tamamlandı say
    comps = st.setdefault("completions", {})
    week_map = comps.setdefault(week, {})
    for t in WEEKLY_TASKS:
        if t.get("auto"):
            week_map[t["key"]] = True

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
    """Startup: sadece Pazar + bu hafta henüz koşmadıysa çalıştır."""
    if not is_sunday():
        return None
    try:
        return run_weekly_maintenance(conn, force=False)
    except Exception as exc:
        print(f"⚠️  weekly maintenance: {exc}")
        return {"ok": False, "error": str(exc)}


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
    show_banner = sunday and pending > 0
    return {
        "today": today.isoformat(),
        "week_key": week,
        "is_sunday": sunday,
        "schedule": "Her Pazar (Europe/Istanbul)",
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
                + (f" · ısıtma gap {gap}g" if gap >= 2 else "")
            ),
        },
        "notes": st.get("notes") or "",
    }
