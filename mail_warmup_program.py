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

COHORT_LEGACY = "legacy"
COHORT_NEW = "new"
COHORTS = (COHORT_LEGACY, COHORT_NEW)

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


def day_plan(day: int, *, cohort: str = COHORT_LEGACY) -> dict:
    """Gün 1–30 için hedef + görev listesi + domain başına önerilen gönderim.

    legacy: mevcut ısınmış domainler (daha yüksek ramp)
    new: yeni domainler (yavaş / güvenli ramp) — asla legacy ile aynı hacimde değil
    """
    d = max(1, min(int(day or 1), TOTAL_DAYS))
    cohort = COHORT_NEW if str(cohort or "").strip().lower() == COHORT_NEW else COHORT_LEGACY

    if cohort == COHORT_NEW:
        if d <= 5:
            per = 10 + (d - 1) * 8  # 10…42
            band = "seed"
            tasks = ["list_scrub", "list_dedupe", "test_send", "spam_check", "bulk_send", "cap_apply"]
        elif d <= 12:
            per = 50 + (d - 6) * 25  # 50…200
            band = "early"
            tasks = ["list_dedupe", "test_send", "bulk_send", "spam_check", "metrics_review", "cap_apply"]
        elif d <= 20:
            per = 220 + (d - 13) * 45  # 220…535
            band = "ramp"
            tasks = ["list_scrub", "bulk_send", "spam_check", "metrics_review", "reply_monitor", "cap_apply"]
        elif d <= 26:
            per = 560 + (d - 21) * 80  # 560…960
            band = "scale"
            tasks = ["list_dedupe", "bulk_send", "metrics_review", "spam_check", "cap_apply"]
        else:
            per = 1000 + (d - 27) * 150  # 1000…1450
            band = "mature"
            tasks = ["bulk_send", "metrics_review", "reply_monitor", "cap_apply", "spam_check"]
        per = min(per, 1800)
        titles = {
            "seed": "Yeni domain — tohum (çok düşük hacim)",
            "early": "Yeni domain — erken ısıtma",
            "ramp": "Yeni domain — yavaş rampa",
            "scale": "Yeni domain — kontrollü ölçek",
            "mature": "Yeni domain — olgunlaşma (hâlâ legacy’den düşük)",
        }
        rules = [
            "Yeni domainleri ESKİ domainlerle aynı kampanyada / aynı hacimde kullanma.",
            "İlk 2 hafta sadece temiz / engaged mini listeler.",
            "Bounce > %3 veya fail spike → o domaini pause.",
            "Legacy programdan bağımsız ilerler — gün numaraları karışmaz.",
        ]
    else:
        # Domain başına günlük hedef (legacy / ısınmış)
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
            "seed": "Eski domain — tohum / düşük hacim",
            "early": "Eski domain — erken ısıtma",
            "ramp": "Eski domain — rampa",
            "scale": "Eski domain — ölçek",
            "mature": "Eski domain — olgun / warm’a yakın",
        }
        rules = [
            "Eski ve yeni domainleri karıştırma — ayrı program, ayrı kampanya.",
            "Günlük hedefi aşma; kalanı yarına bırak.",
            "Bounce > %5 veya fail spike → o domaini pause / burned kontrol.",
            "Sadece temiz / engaged liste; soğuk listenin tamamını yakma.",
        ]

    n_dom = 5
    return {
        "day": d,
        "cohort": cohort,
        "band": band,
        "title": titles.get(band, "Isıtma"),
        "per_domain_target": per,
        "total_target_5": per * n_dom,
        "daily_cap_suggest": min(5000 if cohort == COHORT_LEGACY else 2000, max(80, per + 40)),
        "tasks": [
            {
                "key": k,
                "title": TASK_CATALOG[k]["title"],
                "hint": TASK_CATALOG[k]["hint"],
            }
            for k in tasks
            if k in TASK_CATALOG
        ],
        "rules": rules,
    }


def default_track() -> dict:
    return {
        "active": False,
        "started_on": None,
        "origin_started_on": None,
        "domain_ids": [],
        "completions": {},
        "day_override": None,
        "notes": "",
        "last_banner_date": None,
        "last_cap_sync_date": None,
        "last_realign_date": None,
        "realign_note": "",
    }


def default_state() -> dict:
    return {
        "version": 2,
        "tracks": {
            COHORT_LEGACY: default_track(),
            COHORT_NEW: default_track(),
        },
    }


def _normalize_cohort(value) -> str:
    v = str(value or "").strip().lower()
    return COHORT_NEW if v == COHORT_NEW else COHORT_LEGACY


def load_state(conn) -> dict:
    raw = get_mail_setting(conn, SETTING_KEY, "") or ""
    st = default_state()
    if not raw.strip():
        return st
    try:
        data = json.loads(raw)
        if not isinstance(data, dict):
            return st
    except Exception:
        return st

    # v1 → v2: tek program legacy track’e taşınır
    if int(data.get("version") or 1) < 2 or "tracks" not in data:
        track = default_track()
        for k in track.keys():
            if k in data:
                track[k] = data[k]
        if not isinstance(track.get("completions"), dict):
            track["completions"] = {}
        if not isinstance(track.get("domain_ids"), list):
            track["domain_ids"] = []
        st["tracks"][COHORT_LEGACY] = track
        return st

    tracks = data.get("tracks") or {}
    out = default_state()
    for cohort in COHORTS:
        t = default_track()
        src = tracks.get(cohort) if isinstance(tracks, dict) else None
        if isinstance(src, dict):
            t.update(src)
        if not isinstance(t.get("completions"), dict):
            t["completions"] = {}
        if not isinstance(t.get("domain_ids"), list):
            t["domain_ids"] = []
        out["tracks"][cohort] = t
    return out


def save_state(conn, state: dict) -> None:
    state = dict(state or {})
    state["version"] = 2
    if "tracks" not in state:
        state = default_state()
    upsert_mail_setting(conn, SETTING_KEY, json.dumps(state, ensure_ascii=False))


def get_track(state: dict, cohort: str) -> dict:
    cohort = _normalize_cohort(cohort)
    tracks = state.setdefault("tracks", {})
    if cohort not in tracks or not isinstance(tracks.get(cohort), dict):
        tracks[cohort] = default_track()
    return tracks[cohort]


def compute_day_number(state_or_track: dict, today: str | None = None) -> int:
    """Track dict veya legacy flat state."""
    today = today or _today_str()
    track = state_or_track
    if "tracks" in state_or_track:
        # yanlışlıkla full state geldiyse legacy
        track = get_track(state_or_track, COHORT_LEGACY)
    if track.get("day_override"):
        try:
            return max(1, min(TOTAL_DAYS, int(track["day_override"])))
        except (TypeError, ValueError):
            pass
    started = track.get("started_on")
    if not started or not track.get("active"):
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



def activity_gap_days(conn, track: dict | None = None, *, cohort: str = COHORT_LEGACY) -> int:
    """Son bulk gönderimden (yoksa son checklist) bugüne gün farkı."""
    st = load_state(conn)
    tr = track if track is not None else get_track(st, cohort)
    today = date.fromisoformat(_today_str())
    info = last_program_send_info(conn, tr.get("domain_ids") or [])
    last = None
    if info.get("last_send_date"):
        last = date.fromisoformat(info["last_send_date"])
    if last is None:
        for day_s in (tr.get("completions") or {}):
            try:
                dd = date.fromisoformat(str(day_s)[:10])
            except Exception:
                continue
            if last is None or dd > last:
                last = dd
    if last is None and tr.get("started_on"):
        try:
            last = date.fromisoformat(str(tr["started_on"])[:10])
        except Exception:
            last = None
    if last is None:
        return 0
    return max(0, (today - last).days)


def realign_to_last_send(conn, *, advance: bool = False, cohort: str = COHORT_LEGACY) -> dict:
    """Pasif/hasta günlerinden sonra: son gerçek gönderim gününe hizala."""
    cohort = _normalize_cohort(cohort)
    st = load_state(conn)
    tr = get_track(st, cohort)
    if not tr.get("started_on") or not (tr.get("domain_ids") or []):
        raise ValueError("Hizalanacak program yok — önce ısıtma programını başlat.")

    origin = str(tr.get("origin_started_on") or tr.get("started_on"))[:10]
    tr["origin_started_on"] = origin
    today = date.fromisoformat(_today_str())
    info = last_program_send_info(conn, tr.get("domain_ids") or [])
    last_send_date = info.get("last_send_date")
    raw_resume = 1

    if last_send_date:
        last_d = date.fromisoformat(last_send_date)
        raw_resume = program_day_on_date(origin, last_d)
        gap = max(0, (today - last_d).days)
        if advance and gap == 1:
            raw_resume = min(TOTAL_DAYS, raw_resume + 1)
    else:
        gap = activity_gap_days(conn, tr, cohort=cohort)
        raw_resume = 1
        try:
            rows = _domain_rows(conn, tr.get("domain_ids") or [])
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
        {**tr, "day_override": None, "active": True}, today.isoformat()
    )

    tr["started_on"] = new_started.isoformat()
    tr["day_override"] = None
    tr["active"] = True
    tr["last_realign_date"] = today.isoformat()
    tr["last_cap_sync_date"] = None
    soft_bit = ""
    if resume_day != raw_resume:
        soft_bit = f" · soft {raw_resume}→{resume_day} (gap {gap}g)"
    tr["realign_note"] = (
        f"[{cohort}] last_bulk={last_send_date or 'yok'} (n≥{info.get('min_volume') or MIN_WARMUP_DAY_VOLUME}"
        f"{', cnt=' + str(info.get('last_send_day_count')) if info.get('last_send_day_count') else ''})"
        f" → day {resume_day} (takvim {calendar_day_before} idi) · gap={gap}g"
        f"{soft_bit} · started_on→{tr['started_on']}"
    )
    save_state(conn, st)

    sync = sync_program_caps(conn, cohort=cohort, force=True)
    plan = day_plan(resume_day, cohort=cohort)
    return {
        "ok": True,
        "cohort": cohort,
        "resume_day": resume_day,
        "raw_resume_day": raw_resume,
        "last_send_date": last_send_date,
        "last_send_day_count": info.get("last_send_day_count"),
        "gap_days": gap,
        "calendar_day_before": calendar_day_before,
        "started_on": tr["started_on"],
        "origin_started_on": origin,
        "per_domain_target": plan["per_domain_target"],
        "daily_cap": sync.get("daily_cap") or plan["daily_cap_suggest"],
        "hourly_cap": sync.get("hourly_cap"),
        "domains_updated": sync.get("updated") or 0,
        "note": tr["realign_note"],
    }


def maybe_auto_realign_after_gap(conn, *, cohort: str = COHORT_LEGACY) -> dict | None:
    """Gap ≥ 2 gün ise günde 1 kez son gönderime hizala."""
    cohort = _normalize_cohort(cohort)
    st = load_state(conn)
    tr = get_track(st, cohort)
    if not tr.get("active") or not tr.get("started_on"):
        return None
    today = _today_str()
    if (tr.get("last_realign_date") or "") == today:
        return None
    gap = activity_gap_days(conn, tr, cohort=cohort)
    if gap < 2:
        return None
    try:
        result = realign_to_last_send(conn, advance=False, cohort=cohort)
        result["auto"] = True
        return result
    except Exception as exc:
        print(f"⚠️  auto realign [{cohort}]: {exc}")
        return {"ok": False, "error": str(exc), "cohort": cohort}


def _domain_rows(conn, domain_ids):
    if not domain_ids:
        return []
    ids = [int(x) for x in domain_ids if str(x).isdigit() or isinstance(x, int)]
    if not ids:
        return []
    ph = ",".join(["?"] * len(ids))
    rows = fetchall(
        conn,
        f"""
        SELECT id, domain, warm_status, warm_day, daily_cap, health_score,
               COALESCE(NULLIF(warmup_cohort, ''), 'new') AS warmup_cohort
        FROM mail_domains WHERE id IN ({ph})
        """,
        tuple(ids),
    ) or []
    by_id = {int(r["id"]): dict(r) for r in rows}
    return [by_id[i] for i in ids if i in by_id]


def sync_program_caps(conn, state: dict | None = None, *, cohort: str = COHORT_LEGACY, force: bool = False) -> dict:
    """Aktif track domainlerinin daily_cap’ini bugünün planına çek."""
    cohort = _normalize_cohort(cohort)
    st = state if state is not None else load_state(conn)
    tr = get_track(st, cohort)
    if not tr.get("active") or not (tr.get("domain_ids") or []):
        return {"updated": 0, "skipped": True, "cohort": cohort}
    today = _today_str()
    if not force and (tr.get("last_cap_sync_date") or "") == today:
        return {"updated": 0, "skipped": True, "daily_cap": None, "cohort": cohort}
    day_n = compute_day_number(tr, today)
    plan = day_plan(day_n, cohort=cohort)
    cap = int(plan["daily_cap_suggest"])
    hourly = max(20, min(200, (cap + 19) // 20))
    updated = 0
    for did in tr.get("domain_ids") or []:
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
    tr["last_cap_sync_date"] = today
    save_state(conn, st)
    return {
        "updated": updated,
        "skipped": False,
        "daily_cap": cap,
        "hourly_cap": hourly,
        "day": day_n,
        "per_domain_target": int(plan["per_domain_target"]),
        "cohort": cohort,
    }


def _track_snapshot(conn, st: dict, cohort: str, *, auto_realign=None) -> dict:
    cohort = _normalize_cohort(cohort)
    tr = get_track(st, cohort)
    today = _today_str()
    if tr.get("active"):
        try:
            sync_program_caps(conn, st, cohort=cohort, force=False)
            st = load_state(conn)
            tr = get_track(st, cohort)
        except Exception as exc:
            print(f"⚠️  warmup cap sync [{cohort}]: {exc}")
    day_n = compute_day_number(tr, today)
    plan = day_plan(day_n, cohort=cohort)
    done_map = (tr.get("completions") or {}).get(today) or {}
    tasks = []
    all_done = True
    for t in plan["tasks"]:
        done = bool(done_map.get(t["key"]))
        if not done:
            all_done = False
        tasks.append({**t, "done": done})
    domains = _domain_rows(conn, tr.get("domain_ids") or [])
    suggested = []
    if not domains:
        try:
            raw = fetchall(
                conn,
                """
                SELECT id, domain, warm_status, warm_day, daily_cap, health_score,
                       COALESCE(NULLIF(warmup_cohort, ''), 'new') AS warmup_cohort
                FROM mail_domains
                WHERE COALESCE(NULLIF(warmup_cohort, ''), 'new') = ?
                ORDER BY id ASC LIMIT 20
                """,
                (cohort,),
            ) or []
        except Exception:
            raw = fetchall(
                conn,
                """
                SELECT id, domain, warm_status, warm_day, daily_cap, health_score
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
                "warmup_cohort": d.get("warmup_cohort") or cohort,
            })
            if len(suggested) >= 8:
                break

    incomplete = bool(tr.get("active")) and not all_done
    caps = [int(d.get("daily_cap") or 0) for d in domains if d.get("daily_cap") is not None]
    min_cap = min(caps) if caps else 0
    target = int(plan["per_domain_target"])
    suggest = int(plan["daily_cap_suggest"])
    send_info = last_program_send_info(conn, tr.get("domain_ids") or [])
    gap = activity_gap_days(conn, tr, cohort=cohort)
    label = "Eski" if cohort == COHORT_LEGACY else "Yeni"
    banner_text = ""
    if incomplete:
        banner_text = (
            f"{label} ısıtma Günü {day_n}/{TOTAL_DAYS}: "
            f"{sum(1 for t in tasks if not t['done'])} görev · "
            f"~{target}/domain · cap {min_cap or suggest}"
        )
        if min_cap and min_cap < target:
            banner_text += f" ⚠️ cap düşük"
        if gap >= 2:
            banner_text += f" · gap {gap}g"
    return {
        "cohort": cohort,
        "cohort_label": label,
        "today": today,
        "active": bool(tr.get("active")),
        "started_on": tr.get("started_on"),
        "origin_started_on": tr.get("origin_started_on"),
        "day": day_n,
        "total_days": TOTAL_DAYS,
        "plan": {**plan, "tasks": tasks},
        "all_done_today": all_done if tr.get("active") else False,
        "incomplete": incomplete,
        "domains": domains,
        "suggested_domains": suggested,
        "notes": tr.get("notes") or "",
        "realign_note": tr.get("realign_note") or "",
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


def program_snapshot(conn, *, cohort: str | None = None) -> dict:
    """Tek cohort snapshot veya her iki track + birleşik banner."""
    st = load_state(conn)
    if cohort is not None:
        cohort = _normalize_cohort(cohort)
        auto = None
        if get_track(st, cohort).get("active"):
            try:
                auto = maybe_auto_realign_after_gap(conn, cohort=cohort)
                st = load_state(conn)
            except Exception as exc:
                print(f"⚠️  warmup auto realign: {exc}")
        return _track_snapshot(conn, st, cohort, auto_realign=auto)

    tracks = {}
    banners = []
    for c in COHORTS:
        auto = None
        if get_track(st, c).get("active"):
            try:
                auto = maybe_auto_realign_after_gap(conn, cohort=c)
                st = load_state(conn)
            except Exception as exc:
                print(f"⚠️  warmup auto realign: {exc}")
        snap = _track_snapshot(conn, st, c, auto_realign=auto)
        tracks[c] = snap
        if snap.get("banner", {}).get("show") and snap["banner"].get("text"):
            banners.append(snap["banner"]["text"])

    # UI geriye uyumluluk: «program» = legacy track (+ tracks haritası)
    primary = tracks[COHORT_LEGACY]
    out = {
        **primary,
        "tracks": tracks,
        "banner": {
            "show": bool(banners),
            "text": " · ".join(banners) if banners else primary.get("banner", {}).get("text") or "",
        },
    }
    return out


def _infer_cohort_for_ids(conn, ids: list[int]) -> str:
    if not ids:
        raise ValueError("En az 1 domain seç.")
    ph = ",".join(["?"] * len(ids))
    rows = fetchall(
        conn,
        f"""
        SELECT id, domain, COALESCE(NULLIF(warmup_cohort, ''), 'new') AS warmup_cohort
        FROM mail_domains WHERE id IN ({ph})
        """,
        tuple(ids),
    ) or []
    if len(rows) != len(set(ids)):
        raise ValueError("Bazı domainler bulunamadı.")
    cohorts = {_normalize_cohort(r["warmup_cohort"]) for r in rows}
    if len(cohorts) > 1:
        raise ValueError(
            "Eski ve yeni domainleri aynı programa koyma. "
            "Önce Eski veya Yeni sekmesini seç, yalnız o gruptan domain işaretle."
        )
    return cohorts.pop()


def start_program(conn, domain_ids, notes="", *, cohort: str | None = None) -> dict:
    ids = []
    for x in domain_ids or []:
        try:
            ids.append(int(x))
        except (TypeError, ValueError):
            continue
    ids = ids[:20]
    if len(ids) < 1:
        raise ValueError("En az 1 domain seç.")
    inferred = _infer_cohort_for_ids(conn, ids)
    if cohort is not None and _normalize_cohort(cohort) != inferred:
        raise ValueError(
            f"Seçilen domainler «{inferred}» grubunda; program «{_normalize_cohort(cohort)}» için açılamaz."
        )
    cohort = inferred
    today = _today_str()
    st = load_state(conn)
    tr = get_track(st, cohort)
    tr["active"] = True
    tr["started_on"] = today
    if not tr.get("origin_started_on"):
        tr["origin_started_on"] = today
    tr["domain_ids"] = ids
    tr["day_override"] = None
    tr["notes"] = (notes or "").strip()
    tr["completions"] = tr.get("completions") or {}
    tr["last_cap_sync_date"] = None
    plan = day_plan(1, cohort=cohort)
    for did in ids:
        execute(
            conn,
            """
            UPDATE mail_domains
            SET warm_status = 'warming', warm_day = 1, daily_cap = ?, warmup_cohort = ?
            WHERE id = ?
            """,
            (int(plan["daily_cap_suggest"]), cohort, did),
        )
    save_state(conn, st)
    return program_snapshot(conn)


def set_task(conn, task_key: str, done: bool, day_date: str | None = None, *, cohort: str = COHORT_LEGACY) -> dict:
    if task_key not in TASK_CATALOG:
        raise ValueError("Bilinmeyen görev.")
    cohort = _normalize_cohort(cohort)
    st = load_state(conn)
    tr = get_track(st, cohort)
    if not tr.get("active"):
        raise ValueError("Program aktif değil — önce başlat.")
    today = (day_date or _today_str())[:10]
    comps = tr.setdefault("completions", {})
    day_map = comps.setdefault(today, {})
    day_map[task_key] = bool(done)
    save_state(conn, st)
    snap_day = compute_day_number(tr, today)
    plan = day_plan(snap_day, cohort=cohort)
    keys = [t["key"] for t in plan["tasks"]]
    all_done = bool(keys) and all(day_map.get(k) for k in keys)
    if done and (task_key == "cap_apply" or all_done):
        try:
            sync_program_caps(conn, st, cohort=cohort, force=True)
        except Exception as exc:
            print(f"⚠️  warmup cap_apply sync: {exc}")
    return program_snapshot(conn)


def patch_program(conn, data: dict) -> dict:
    cohort = _normalize_cohort(data.get("cohort") or COHORT_LEGACY)
    st = load_state(conn)
    tr = get_track(st, cohort)
    if "notes" in data:
        tr["notes"] = str(data.get("notes") or "")
    if "day_override" in data:
        v = data.get("day_override")
        if v in (None, "", 0, "0"):
            tr["day_override"] = None
        else:
            tr["day_override"] = max(1, min(TOTAL_DAYS, int(v)))
    if "domain_ids" in data and isinstance(data["domain_ids"], list):
        ids = []
        for x in data["domain_ids"]:
            try:
                ids.append(int(x))
            except (TypeError, ValueError):
                continue
        if ids:
            _infer_cohort_for_ids(conn, ids)  # aynı cohort doğrula
        tr["domain_ids"] = ids[:20]
    if data.get("pause"):
        tr["active"] = False
    if data.get("resume") and tr.get("started_on") and tr.get("domain_ids"):
        tr["active"] = True
    save_state(conn, st)
    return program_snapshot(conn)
