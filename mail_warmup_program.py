"""Mikromail — insan operatörü için 30 günlük domain ısıtma programı.

State: mail_settings.warmup_program_v1 (JSON)
Takvim günü bazlı checklist; worker warm_day tick'inden bağımsız.
"""
from __future__ import annotations

import json
from datetime import date, datetime, timezone

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

SETTING_KEY = "warmup_program_v1"
TOTAL_DAYS = 30
# Operatör günü: Türkiye gece yarısı (00:00) sonrası yeni checklist
OP_TZ = ZoneInfo("Europe/Istanbul") if ZoneInfo else timezone.utc

# Görev kataloğu (UI + API)
TASK_CATALOG = {
    "list_scrub": {
        "title": "Liste temizliği (scrub)",
        "hint": "Kontak → scrub başlat veya yeni eklenenleri syntax/MX kontrol et. Invalid’leri suppression’a al.",
    },
    "list_dedupe": {
        "title": "Liste ayıklama",
        "hint": "Mükerrer / boş / rol adreslerini (info@) ayıkla. Bugün göndereceğin listeyi hazırla.",
    },
    "spam_check": {
        "title": "Spam klasörü kontrolü",
        "hint": "Test Gmail/Outlook’ta Spam’e düştü mü bak. Düştüyse ‘Spam değil’ işaretle.",
    },
    "test_send": {
        "title": "Test mail (kendi kutuların)",
        "hint": "Her ısıtılan domainden 1–3 test mail (Gmail + Outlook). Aç / tıkla.",
    },
    "bulk_send": {
        "title": "Günlük bulk gönderim",
        "hint": "Programdaki domain başına günlük kotayı aşma. Engaged / temiz liste kullan.",
    },
    "metrics_review": {
        "title": "Metrik gözden geçirme",
        "hint": "Bounce / fail / şikâyet oranına bak. Spike varsa o domaini pause et.",
    },
    "cap_apply": {
        "title": "Domain cap güncelle",
        "hint": "İşaretleyince daily_cap otomatik bugünün hedefine çekilir. Banner’daki ‘önerilen’ ≠ gönderim kotası; kotayı bu görev / otomatik senkron yazar.",
    },
    "reply_monitor": {
        "title": "Bounce / reply izleme",
        "hint": "DirectMail bounce paneli + gönderim logları. Reply beklenmez (554 normal).",
    },
}


def _today_str() -> str:
    return datetime.now(OP_TZ).date().isoformat()


def day_plan(day: int) -> dict:
    """Gün 1–30 için hedef + görev listesi + domain başına önerilen gönderim."""
    d = max(1, min(int(day or 1), TOTAL_DAYS))
    # Domain başına günlük hedef (5 domain × bu = toplam)
    if d <= 3:
        per = 20 + (d - 1) * 15  # 20, 35, 50
        band = "seed"
        tasks = ["list_scrub", "list_dedupe", "test_send", "spam_check", "bulk_send", "cap_apply"]
    elif d <= 7:
        per = 80 + (d - 4) * 40  # 80…200
        band = "early"
        tasks = ["list_dedupe", "test_send", "bulk_send", "spam_check", "metrics_review", "cap_apply"]
    elif d <= 14:
        per = 250 + (d - 8) * 80  # 250…730
        band = "ramp"
        tasks = ["list_scrub", "bulk_send", "spam_check", "metrics_review", "reply_monitor", "cap_apply"]
    elif d <= 21:
        per = 800 + (d - 15) * 150  # 800…1700
        band = "scale"
        tasks = ["list_dedupe", "bulk_send", "metrics_review", "spam_check", "cap_apply"]
    else:
        per = 1800 + (d - 22) * 200  # 1800…3400
        band = "mature"
        tasks = ["bulk_send", "metrics_review", "reply_monitor", "cap_apply", "spam_check"]

    per = min(per, 4000)
    titles = {
        "seed": "Tohum günleri — çok düşük hacim, itibar kur",
        "early": "Erken ısıtma — yavaş artır, spam’i izle",
        "ramp": "Rampa — hacim büyür, liste hijyeni şart",
        "scale": "Ölçek — domainleri rotasyonla kullan",
        "mature": "Olgunlaşma — warm’a yaklaş, cap yükselt",
    }
    return {
        "day": d,
        "band": band,
        "title": titles.get(band, "Isıtma"),
        "per_domain_target": per,
        "total_target_5": per * 5,
        "daily_cap_suggest": min(5000, max(100, per + 50)),
        "tasks": [
            {
                "key": k,
                "title": TASK_CATALOG[k]["title"],
                "hint": TASK_CATALOG[k]["hint"],
            }
            for k in tasks
            if k in TASK_CATALOG
        ],
        "rules": [
            "Aynı içerik/şablonu 5 domainde peş peşe spam gibi atma — rotasyon yap.",
            "Günlük hedefi aşma; kalanı yarına bırak.",
            "Bounce > %5 veya fail spike → o domaini pause / burned kontrol.",
            "Sadece temiz / engaged liste; yeni soğuk listenin tamamını ilk hafta yakma.",
            "DirectMail’e gelen reply 554 normal — ısınma için cevap şart değil.",
        ],
    }


def default_state() -> dict:
    return {
        "version": 1,
        "started_on": None,
        "active": False,
        "domain_ids": [],
        "completions": {},  # "YYYY-MM-DD": { "task_key": true, ... }
        "day_override": None,  # manuel gün (opsiyonel)
        "notes": "",
        "last_banner_date": None,
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
    if not isinstance(st.get("domain_ids"), list):
        st["domain_ids"] = []
    return st


def save_state(conn, state: dict) -> None:
    upsert_mail_setting(conn, SETTING_KEY, json.dumps(state, ensure_ascii=False))


def compute_day_number(state: dict, today: str | None = None) -> int:
    today = today or _today_str()
    if state.get("day_override"):
        try:
            return max(1, min(TOTAL_DAYS, int(state["day_override"])))
        except (TypeError, ValueError):
            pass
    started = state.get("started_on")
    if not started or not state.get("active"):
        return 1
    try:
        d0 = date.fromisoformat(str(started)[:10])
        d1 = date.fromisoformat(today[:10])
        n = (d1 - d0).days + 1
        return max(1, min(TOTAL_DAYS, n))
    except Exception:
        return 1


def _domain_rows(conn, domain_ids):
    if not domain_ids:
        return []
    ids = [int(x) for x in domain_ids if str(x).isdigit() or isinstance(x, int)]
    if not ids:
        return []
    ph = ",".join(["?"] * len(ids))
    rows = fetchall(
        conn,
        f"SELECT id, domain, warm_status, warm_day, daily_cap, health_score FROM mail_domains WHERE id IN ({ph})",
        tuple(ids),
    ) or []
    by_id = {int(r["id"]): dict(r) for r in rows}
    return [by_id[i] for i in ids if i in by_id]


def sync_program_caps(conn, state: dict | None = None, *, force: bool = False) -> dict:
    """Aktif program domainlerinin daily_cap’ini bugünün planına çek.

    Banner ‘~410’ öneri; göndermeyi engelleyen asıl kapı domain.daily_cap.
    Cap eski günde kalırsa (örn. 250) kalan mailler skipped olur — her gün 1 kez senkron.
    """
    st = state if state is not None else load_state(conn)
    if not st.get("active") or not (st.get("domain_ids") or []):
        return {"updated": 0, "skipped": True}
    today = _today_str()
    if not force and (st.get("last_cap_sync_date") or "") == today:
        return {"updated": 0, "skipped": True, "daily_cap": None}
    day_n = compute_day_number(st, today)
    plan = day_plan(day_n)
    cap = int(plan["daily_cap_suggest"])
    updated = 0
    for did in st.get("domain_ids") or []:
        try:
            execute(
                conn,
                """
                UPDATE mail_domains
                SET daily_cap = ?,
                    warm_day = ?,
                    warm_status = CASE
                        WHEN COALESCE(warm_status, '') IN ('burned', 'paused') THEN warm_status
                        WHEN ? >= 30 THEN 'warm'
                        ELSE 'warming'
                    END
                WHERE id = ?
                """,
                (cap, int(day_n), int(day_n), int(did)),
            )
            updated += 1
        except Exception:
            continue
    st["last_cap_sync_date"] = today
    save_state(conn, st)
    return {
        "updated": updated,
        "skipped": False,
        "daily_cap": cap,
        "day": day_n,
        "per_domain_target": int(plan["per_domain_target"]),
    }


def program_snapshot(conn) -> dict:
    st = load_state(conn)
    today = _today_str()
    # Cap ile program hedefini aynı güne kilitle (yoksa 410 öner / 250 kes)
    if st.get("active"):
        try:
            sync_program_caps(conn, st, force=False)
            st = load_state(conn)
        except Exception as exc:
            print(f"⚠️  warmup cap sync: {exc}")
    day_n = compute_day_number(st, today)
    plan = day_plan(day_n)
    done_map = st.get("completions", {}).get(today) or {}
    tasks = []
    all_done = True
    for t in plan["tasks"]:
        done = bool(done_map.get(t["key"]))
        if not done:
            all_done = False
        tasks.append({**t, "done": done})
    domains = _domain_rows(conn, st.get("domain_ids") or [])
    # Aktif değilse önerilen 5 domain (ready/smtp olanlar öncelik)
    suggested = []
    if not domains:
        raw = fetchall(
            conn,
            """
            SELECT id, domain, warm_status, warm_day, daily_cap, health_score,
                   smtp_password, smtp_password_enc
            FROM mail_domains ORDER BY id ASC LIMIT 20
            """,
        ) or []
        for r in raw:
            d = dict(r)
            suggested.append({
                "id": d["id"],
                "domain": d["domain"],
                "warm_status": d.get("warm_status"),
                "daily_cap": d.get("daily_cap"),
            })
            if len(suggested) >= 5:
                break

    incomplete = bool(st.get("active")) and not all_done
    caps = [int(d.get("daily_cap") or 0) for d in domains if d.get("daily_cap") is not None]
    min_cap = min(caps) if caps else 0
    target = int(plan["per_domain_target"])
    suggest = int(plan["daily_cap_suggest"])
    banner_text = ""
    if incomplete:
        banner_text = (
            f"Isıtma Günü {day_n}/{TOTAL_DAYS}: "
            f"{sum(1 for t in tasks if not t['done'])} görev bekliyor · "
            f"önerilen gönderim ~{target}/domain · günlük cap {min_cap or suggest}"
        )
        if min_cap and min_cap < target:
            banner_text += f" ⚠️ cap hedefin altında (en az {target} olmalı)"
    return {
        "today": today,
        "active": bool(st.get("active")),
        "started_on": st.get("started_on"),
        "day": day_n,
        "total_days": TOTAL_DAYS,
        "plan": {**plan, "tasks": tasks},
        "all_done_today": all_done if st.get("active") else False,
        "incomplete": incomplete,
        "domains": domains,
        "suggested_domains": suggested,
        "notes": st.get("notes") or "",
        "cap_reality": {
            "min_daily_cap": min_cap,
            "per_domain_target": target,
            "daily_cap_suggest": suggest,
            "aligned": (not min_cap) or min_cap >= target,
        },
        "banner": {
            "show": incomplete,
            "text": banner_text,
        },
    }


def start_program(conn, domain_ids, notes="") -> dict:
    ids = []
    for x in domain_ids or []:
        try:
            ids.append(int(x))
        except (TypeError, ValueError):
            continue
    ids = ids[:8]
    if len(ids) < 1:
        raise ValueError("En az 1 domain seç.")
    today = _today_str()
    st = load_state(conn)
    st["active"] = True
    st["started_on"] = today
    st["domain_ids"] = ids
    st["day_override"] = None
    st["notes"] = (notes or "").strip()
    st["completions"] = st.get("completions") or {}
    # Seçili domainleri warming + cap seed
    plan = day_plan(1)
    for did in ids:
        execute(
            conn,
            """
            UPDATE mail_domains
            SET warm_status = 'warming', warm_day = 1, daily_cap = ?
            WHERE id = ?
            """,
            (int(plan["daily_cap_suggest"]), did),
        )
    save_state(conn, st)
    return program_snapshot(conn)


def set_task(conn, task_key: str, done: bool, day_date: str | None = None) -> dict:
    if task_key not in TASK_CATALOG:
        raise ValueError("Bilinmeyen görev.")
    st = load_state(conn)
    if not st.get("active"):
        raise ValueError("Program aktif değil — önce başlat.")
    today = (day_date or _today_str())[:10]
    comps = st.setdefault("completions", {})
    day_map = comps.setdefault(today, {})
    day_map[task_key] = bool(done)
    save_state(conn, st)
    # «Domain cap güncelle» işaretlenince veya günün tüm görevleri bitince cap’i plana çek
    snap_day = compute_day_number(st, today)
    plan = day_plan(snap_day)
    keys = [t["key"] for t in plan["tasks"]]
    all_done = bool(keys) and all(day_map.get(k) for k in keys)
    if done and (task_key == "cap_apply" or all_done):
        try:
            sync_program_caps(conn, st, force=True)
        except Exception as exc:
            print(f"⚠️  warmup cap_apply sync: {exc}")
    return program_snapshot(conn)


def patch_program(conn, data: dict) -> dict:
    st = load_state(conn)
    if "notes" in data:
        st["notes"] = str(data.get("notes") or "")
    if "day_override" in data:
        v = data.get("day_override")
        if v in (None, "", 0, "0"):
            st["day_override"] = None
        else:
            st["day_override"] = max(1, min(TOTAL_DAYS, int(v)))
    if "domain_ids" in data and isinstance(data["domain_ids"], list):
        ids = []
        for x in data["domain_ids"]:
            try:
                ids.append(int(x))
            except (TypeError, ValueError):
                continue
        st["domain_ids"] = ids[:8]
    if data.get("pause"):
        st["active"] = False
    if data.get("resume") and st.get("started_on") and st.get("domain_ids"):
        st["active"] = True
    save_state(conn, st)
    return program_snapshot(conn)
