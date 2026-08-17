"""Mikromail — insan operatörü için 30 günlük domain ısıtma programı.

State: mail_settings.warmup_program_v1 (JSON)
Takvim günü bazlı checklist; worker warm_day tick'inden bağımsız.
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
    fetchone,
    get_mail_setting,
    upsert_mail_setting,
)

SETTING_KEY = "warmup_program_v1"
TOTAL_DAYS = 30
# Operatör günü: Türkiye gece yarısı (00:00) sonrası yeni checklist
OP_TZ = ZoneInfo("Europe/Istanbul") if ZoneInfo else timezone.utc
# Test/ Tolga Test gibi 3–5’lik denemeler «son bulk günü» sayılmasın
MIN_WARMUP_DAY_VOLUME = 25
# Gap ≥ bu kadar gün → resume gününü yumuşat (hacim şişmesin)
GAP_SOFT_MIN_DAYS = 5

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


def _parse_op_date(value) -> date | None:
    """sent_at / ISO / 'YYYY-MM-DD …' → operatör (TR) tarihi."""
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(OP_TZ).date()
    text = str(value).strip()
    if not text:
        return None
    try:
        if len(text) >= 10 and text[4] == "-" and text[7] == "-":
            # Önce tarih kısmı
            try:
                return date.fromisoformat(text[:10])
            except Exception:
                pass
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        if " " in text and "T" not in text:
            text = text.replace(" ", "T", 1)
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(OP_TZ).date()
    except Exception:
        return None


def program_day_on_date(started_on: str, on_date: str | date) -> int:
    """started_on → on_date arası program günü (1..30). day_override yok sayılır."""
    try:
        d0 = date.fromisoformat(str(started_on)[:10])
        if isinstance(on_date, date):
            d1 = on_date
        else:
            d1 = date.fromisoformat(str(on_date)[:10])
        return max(1, min(TOTAL_DAYS, (d1 - d0).days + 1))
    except Exception:
        return 1


def _send_day_expr(column: str = "COALESCE(sent_at, created_at)") -> str:
    """SQL: gönderim anını takvim gününe (YYYY-MM-DD) çevir — PG + SQLite ISO text."""
    # Prod ISO string veya timestamptz; substr her iki tarafta da güvenli
    return f"substr(CAST({column} AS TEXT), 1, 10)"


def last_program_send_info(conn, domain_ids=None, *, min_volume: int | None = None) -> dict:
    """Program domainlerinden son *anlamlı* bulk günü (TR).

    3’lük Tolga Test gibi mikro gönderimler gap/realign’i bozmasın diye
    günde en az MIN_WARMUP_DAY_VOLUME başarılı send gerekir.
    """
    ids = []
    for x in (domain_ids or []):
        try:
            ids.append(int(x))
        except (TypeError, ValueError):
            continue
    min_vol = int(min_volume if min_volume is not None else MIN_WARMUP_DAY_VOLUME)
    min_vol = max(1, min_vol)
    day_expr = _send_day_expr()
    row = None
    try:
        if ids:
            ph = ",".join(["?"] * len(ids))
            row = fetchone(
                conn,
                f"""
                SELECT send_day, cnt FROM (
                    SELECT {day_expr} AS send_day, COUNT(*) AS cnt
                    FROM mail_sends
                    WHERE status IN ('sent', 'simulated')
                      AND domain_id IN ({ph})
                    GROUP BY 1
                ) t
                WHERE cnt >= ?
                ORDER BY send_day DESC
                LIMIT 1
                """,
                tuple(ids) + (min_vol,),
            )
        else:
            row = fetchone(
                conn,
                f"""
                SELECT send_day, cnt FROM (
                    SELECT {day_expr} AS send_day, COUNT(*) AS cnt
                    FROM mail_sends
                    WHERE status IN ('sent', 'simulated')
                    GROUP BY 1
                ) t
                WHERE cnt >= ?
                ORDER BY send_day DESC
                LIMIT 1
                """,
                (min_vol,),
            )
    except Exception as exc:
        print(f"⚠️  last_program_send_info volume: {exc}")
        row = None
        # Fallback: herhangi bir son send (eski davranış)
        try:
            if ids:
                ph = ",".join(["?"] * len(ids))
                row = fetchone(
                    conn,
                    f"""
                    SELECT MAX(sent_at) AS last_sent, MAX(created_at) AS last_created
                    FROM mail_sends
                    WHERE status IN ('sent', 'simulated')
                      AND domain_id IN ({ph})
                    """,
                    tuple(ids),
                )
            else:
                row = fetchone(
                    conn,
                    """
                    SELECT MAX(sent_at) AS last_sent, MAX(created_at) AS last_created
                    FROM mail_sends
                    WHERE status IN ('sent', 'simulated')
                    """,
                )
        except Exception as exc2:
            print(f"⚠️  last_program_send_info fallback: {exc2}")
            row = None

    last_d = None
    day_count = None
    raw = None
    if row:
        try:
            d = dict(row)
        except Exception:
            d = row
        try:
            if d.get("send_day") is not None:
                last_d = _parse_op_date(d.get("send_day"))
                try:
                    day_count = int(d.get("cnt") or 0)
                except (TypeError, ValueError):
                    day_count = None
            else:
                raw = d.get("last_sent") or d.get("last_created")
                last_d = _parse_op_date(raw)
        except Exception:
            try:
                raw = row["last_sent"] or row["last_created"]
                last_d = _parse_op_date(raw)
            except Exception:
                pass
    return {
        "last_send_at": str(raw) if raw else (last_d.isoformat() if last_d else None),
        "last_send_date": last_d.isoformat() if last_d else None,
        "last_send_day_count": day_count,
        "min_volume": min_vol,
        "domain_ids": ids,
    }


def gap_soft_resume_day(resume_day: int, gap_days: int) -> int:
    """Uzun sessizlikten dönüşte program gününü geri çek (itibar koruma).

    gap 5–6 → −2 … gap 14+ → −7 (min gün 5). Takvim şişmesi zaten
    realign ile kesilir; bu ek olarak «10 gün sessiz → yine 1100/domain» riskini keser.
    """
    d = max(1, min(TOTAL_DAYS, int(resume_day or 1)))
    gap = max(0, int(gap_days or 0))
    if gap < GAP_SOFT_MIN_DAYS:
        return d
    penalty = min(10, max(2, gap // 2))
    return max(5, d - penalty)


def activity_gap_days(conn, state: dict | None = None) -> int:
    """Son bulk gönderimden (yoksa son checklist) bugüne gün farkı."""
    st = state if state is not None else load_state(conn)
    today = date.fromisoformat(_today_str())
    info = last_program_send_info(conn, st.get("domain_ids") or [])
    last = None
    if info.get("last_send_date"):
        last = date.fromisoformat(info["last_send_date"])
    if last is None:
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


def realign_to_last_send(conn, *, advance: bool = False) -> dict:
    """Pasif/hasta günlerinden sonra: son gerçek gönderim gününe hizala.

    Takvim «her gün yaptın» diye gün 16’ya zıplamasın; son mail günündeki
    program gününün cap/hedefini bugüne yazar (started_on re-anchor).
    Uzun gap’te soft rollback ile hacmi düşürür.
    """
    st = load_state(conn)
    if not st.get("started_on") or not (st.get("domain_ids") or []):
        raise ValueError("Hizalanacak program yok — önce ısıtma programını başlat.")

    origin = str(st.get("origin_started_on") or st.get("started_on"))[:10]
    st["origin_started_on"] = origin
    today = date.fromisoformat(_today_str())
    info = last_program_send_info(conn, st.get("domain_ids") or [])
    last_send_date = info.get("last_send_date")
    raw_resume = 1

    if last_send_date:
        last_d = date.fromisoformat(last_send_date)
        raw_resume = program_day_on_date(origin, last_d)
        gap = max(0, (today - last_d).days)
        # Tek gün ara + advance → ertesi programa geç; uzun gap’te soft rollback
        if advance and gap == 1:
            raw_resume = min(TOTAL_DAYS, raw_resume + 1)
    else:
        # Hiç anlamlı send yok — domain warm_day / checklist’ten tahmin
        gap = activity_gap_days(conn, st)
        raw_resume = 1
        try:
            rows = _domain_rows(conn, st.get("domain_ids") or [])
            wd = [int(r.get("warm_day") or 0) for r in rows]
            if wd:
                raw_resume = max(1, min(TOTAL_DAYS, max(wd)))
        except Exception:
            pass
        last_send_date = None

    resume_day = gap_soft_resume_day(raw_resume, gap)
    resume_day = max(1, min(TOTAL_DAYS, int(resume_day)))
    new_started = today - timedelta(days=resume_day - 1)
    calendar_day_before = compute_day_number(
        {**st, "day_override": None, "active": True}, today.isoformat()
    )

    st["started_on"] = new_started.isoformat()
    st["day_override"] = None
    st["active"] = True
    st["last_realign_date"] = today.isoformat()
    st["last_cap_sync_date"] = None  # cap’i zorla yeniden yaz
    soft_bit = ""
    if resume_day != raw_resume:
        soft_bit = f" · soft {raw_resume}→{resume_day} (gap {gap}g)"
    st["realign_note"] = (
        f"last_bulk={last_send_date or 'yok'} (n≥{info.get('min_volume') or MIN_WARMUP_DAY_VOLUME}"
        f"{', cnt=' + str(info.get('last_send_day_count')) if info.get('last_send_day_count') else ''})"
        f" → day {resume_day} (takvim {calendar_day_before} idi) · gap={gap}g"
        f"{soft_bit} · started_on→{st['started_on']}"
    )
    save_state(conn, st)

    sync = sync_program_caps(conn, st, force=True)
    plan = day_plan(resume_day)
    return {
        "ok": True,
        "resume_day": resume_day,
        "raw_resume_day": raw_resume,
        "last_send_date": last_send_date,
        "last_send_day_count": info.get("last_send_day_count"),
        "gap_days": gap,
        "calendar_day_before": calendar_day_before,
        "started_on": st["started_on"],
        "origin_started_on": origin,
        "per_domain_target": plan["per_domain_target"],
        "daily_cap": sync.get("daily_cap") or plan["daily_cap_suggest"],
        "hourly_cap": sync.get("hourly_cap"),
        "domains_updated": sync.get("updated") or 0,
        "note": st["realign_note"],
    }


def maybe_auto_realign_after_gap(conn) -> dict | None:
    """Gap ≥ 2 gün ise günde 1 kez son gönderime hizala (hasta/pasif dönüşü)."""
    st = load_state(conn)
    if not st.get("active") or not st.get("started_on"):
        return None
    today = _today_str()
    if (st.get("last_realign_date") or "") == today:
        return None
    gap = activity_gap_days(conn, st)
    if gap < 2:
        return None
    try:
        result = realign_to_last_send(conn, advance=False)
        result["auto"] = True
        return result
    except Exception as exc:
        print(f"⚠️  auto realign: {exc}")
        return {"ok": False, "error": str(exc)}


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
    hourly_cap ≈ daily/20 (en az 30, en fazla 200) — gün boyu yayılım.
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
    hourly = max(30, min(200, (cap + 19) // 20))
    updated = 0
    for did in st.get("domain_ids") or []:
        try:
            execute(
                conn,
                """
                UPDATE mail_domains
                SET daily_cap = ?,
                    hourly_cap = ?,
                    warm_day = ?,
                    warm_status = CASE
                        WHEN COALESCE(warm_status, '') IN ('burned', 'paused') THEN warm_status
                        WHEN ? >= 30 THEN 'warm'
                        ELSE 'warming'
                    END
                WHERE id = ?
                """,
                (cap, hourly, int(day_n), int(day_n), int(did)),
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
        "hourly_cap": hourly,
        "day": day_n,
        "per_domain_target": int(plan["per_domain_target"]),
    }


def program_snapshot(conn) -> dict:
    st = load_state(conn)
    today = _today_str()
    auto_realign = None
    if st.get("active"):
        try:
            auto_realign = maybe_auto_realign_after_gap(conn)
            st = load_state(conn)
        except Exception as exc:
            print(f"⚠️  warmup auto realign: {exc}")
        # Cap ile program hedefini aynı güne kilitle (yoksa 410 öner / 250 kes)
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
    send_info = last_program_send_info(conn, st.get("domain_ids") or [])
    gap = activity_gap_days(conn, st)
    banner_text = ""
    if incomplete:
        banner_text = (
            f"Isıtma Günü {day_n}/{TOTAL_DAYS}: "
            f"{sum(1 for t in tasks if not t['done'])} görev bekliyor · "
            f"önerilen gönderim ~{target}/domain · günlük cap {min_cap or suggest}"
        )
        if min_cap and min_cap < target:
            banner_text += f" ⚠️ cap hedefin altında (en az {target} olmalı)"
        if gap >= 2:
            banner_text += f" · son gönderim gap {gap}g"
    return {
        "today": today,
        "active": bool(st.get("active")),
        "started_on": st.get("started_on"),
        "origin_started_on": st.get("origin_started_on"),
        "day": day_n,
        "total_days": TOTAL_DAYS,
        "plan": {**plan, "tasks": tasks},
        "all_done_today": all_done if st.get("active") else False,
        "incomplete": incomplete,
        "domains": domains,
        "suggested_domains": suggested,
        "notes": st.get("notes") or "",
        "realign_note": st.get("realign_note") or "",
        "last_send_date": send_info.get("last_send_date"),
        "activity_gap_days": gap,
        "auto_realign": auto_realign,
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
