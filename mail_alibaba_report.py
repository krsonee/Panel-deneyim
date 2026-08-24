"""Alibaba Cloud DirectMail OpenAPI — gerçek teslimat/bounce raporu senkronu.

Sorun (22.08.2026): Mikromail paneli sadece SMTP submission (Alibaba'nın
"250 OK" ile kabul etmesi) durumunu biliyor; gerçek teslimat / bounce /
spam-şikayeti / geçersiz-adres sonucu SADECE Alibaba DirectMail konsolunda
görünüyordu. Bu yüzden panel ~%96-97 "başarı" gösterirken Alibaba konsolu
aynı dönem için ~%60-80 gösteriyordu — ikisi de "doğru" ama farklı şeyi
ölçüyordu (kabul vs gerçek teslimat).

Bu modül SADECE OKUMA yapan (dm:SenderStatisticsDetailByParam — access
level "list") bir API çağrısı ile Alibaba'nın gördüğü gerçek sonucu çeker
ve mail_sends.real_status alanına yazar. Hiçbir gönderim/yapılandırma
değişikliği yapmaz, Alibaba hesabına yazma erişimi GEREKMEZ — sadece
okuma izni yeterli (mümkünse RAM alt-kullanıcısına sadece bu izni verin).

Aliyun "RPC style" v1 imzalama (HMAC-SHA1) — resmi Python SDK'sı olmayan
eski DirectMail (2015-11-23) API ailesi için standart imzalama şeması.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import time
import urllib.parse
import urllib.request
import urllib.error
import uuid
import json
from datetime import datetime, timedelta, timezone

import re

from database import (
    execute,
    fetchall,
    fetchone,
    get_mail_setting,
    iso,
    scalar,
    upsert_mail_setting,
    utcnow,
)

SETTING_AK_ID = "alibaba_report_ak_id"
SETTING_AK_SECRET = "alibaba_report_ak_secret"
SETTING_ENABLED = "alibaba_report_enabled"
SETTING_REGION = "alibaba_report_region"
SETTING_LAST_SYNC = "alibaba_report_last_sync_utc"
SETTING_VERIFIED = "alibaba_report_verified"

DEFAULT_REGION = "ap-southeast-1"
API_VERSION = "2015-11-23"

# Alibaba Status kodu -> bizim real_status değerimiz
_STATUS_MAP = {
    0: "delivered",
    2: "invalid",
    3: "spam",
    4: "failed",
}

# Gmail 5.7.1 "messages from [IP] weren't sent" = IP itibarı, kutu ölü değil.
# OverQuota = kutu dolu. Bunları invalid işaretleme.
_SOFT_FAIL_RE = re.compile(
    r"5\.7\.1|weren't sent|overquota|over quota|4\.2\.2|5\.2\.2|"
    r"greylist|try again|temporarily|rate limit|timeout",
    re.I,
)
_DEAD_ADDR_RE = re.compile(
    r"invalid rcptto|559\s|5\.1\.1|user unknown|no such user|"
    r"mailbox not found|does not exist|unrouteable|"
    r"bounce suppression list|account-level bounce",
    re.I,
)


def _is_dead_mailbox(real_status, message) -> bool:
    """Alibaba sonucundan 'bu adrese bir daha atma' kararı.

    invalid (status 2) ve 559/bounce-suppression → ölü.
    5.7.1 IP bloğu / kutu dolu → ölü değil, tekrar denenebilir (farklı IP/gün).
    """
    st = (real_status or "").strip().lower()
    msg = message or ""
    if st == "invalid":
        return True
    if _SOFT_FAIL_RE.search(msg) and not _DEAD_ADDR_RE.search(msg):
        return False
    if _DEAD_ADDR_RE.search(msg):
        return True
    return False


def _mark_contact_dead(conn, *, contact_id, email, detail):
    """Ölü adresi bir daha kampanyaya sokma — verify_status + suppression."""
    email = (email or "").strip().lower()
    if not email and not contact_id:
        return False
    now = iso(utcnow())
    detail = (detail or "alibaba_invalid")[:240]
    if contact_id:
        try:
            existing = fetchone(
                conn,
                "SELECT verify_status FROM mail_contacts WHERE id = ?",
                (int(contact_id),),
            )
            if existing and str(existing["verify_status"] or "").lower() in ("invalid", "disposable"):
                return False
            execute(
                conn,
                """
                UPDATE mail_contacts
                SET verify_status = 'invalid',
                    verify_detail = ?,
                    verified_at = ?,
                    updated_at = ?
                WHERE id = ?
                  AND LOWER(COALESCE(verify_status, '')) NOT IN ('invalid', 'disposable')
                """,
                (detail, now, now, int(contact_id)),
            )
            try:
                from mail_scrub import _set_verify_tags
                _set_verify_tags(conn, int(contact_id), "invalid", now)
            except Exception:
                pass
        except Exception as exc:
            print(f"⚠️  alibaba dead-contact stamp: {exc}")
    if email:
        try:
            from mail_ops import suppress_email
            suppress_email(conn, email, reason="invalid", source="alibaba_report")
        except Exception as exc:
            print(f"⚠️  alibaba dead-contact suppress: {exc}")
    return True


def apply_send_outcome_to_contact(conn, send_id, real_status, message):
    if not _is_dead_mailbox(real_status, message):
        return False
    row = fetchone(
        conn,
        "SELECT contact_id, to_email FROM mail_sends WHERE id = ?",
        (int(send_id),),
    )
    if not row:
        return False
    return _mark_contact_dead(
        conn,
        contact_id=row["contact_id"] if row["contact_id"] else None,
        email=row["to_email"],
        detail=f"alibaba:{real_status} {(message or '')[:180]}",
    )


def backfill_dead_from_reports(conn, *, limit=4000):
    """Tarihsel Alibaba invalid / bounce-list kayıtlarını kontağa işle."""
    rows = fetchall(
        conn,
        """
        SELECT s.id, s.contact_id, s.to_email, s.real_status, s.real_status_message
        FROM mail_sends s
        WHERE s.real_status IN ('invalid', 'failed')
        ORDER BY s.id DESC
        LIMIT ?
        """,
        (int(limit),),
    ) or []
    n = 0
    for r in rows:
        if not _is_dead_mailbox(r["real_status"], r["real_status_message"]):
            continue
        if _mark_contact_dead(
            conn,
            contact_id=r["contact_id"] if r["contact_id"] else None,
            email=r["to_email"],
            detail=f"alibaba:{r['real_status']} {(r['real_status_message'] or '')[:180]}",
        ):
            n += 1
    if n:
        try:
            conn.commit()
        except Exception:
            pass
    return n


def _endpoint(region: str) -> str:
    region = (region or DEFAULT_REGION).strip() or DEFAULT_REGION
    if region in ("cn", "china", "classic", ""):
        return "dm.aliyuncs.com"
    return f"dm.{region}.aliyuncs.com"


def _percent_encode(s) -> str:
    res = urllib.parse.quote(str(s), safe="")
    res = res.replace("+", "%20")
    res = res.replace("*", "%2A")
    res = res.replace("%7E", "~")
    return res


def _sign(secret: str, string_to_sign: str) -> str:
    h = hmac.new((secret + "&").encode("utf-8"), string_to_sign.encode("utf-8"), hashlib.sha1)
    return base64.b64encode(h.digest()).decode("utf-8")


def _build_signed_params(ak_id: str, ak_secret: str, action: str, extra: dict) -> dict:
    params = {
        "Format": "JSON",
        "Version": API_VERSION,
        "AccessKeyId": ak_id,
        "SignatureMethod": "HMAC-SHA1",
        "SignatureVersion": "1.0",
        "SignatureNonce": uuid.uuid4().hex,
        "Timestamp": datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "Action": action,
    }
    for k, v in extra.items():
        if v is None or v == "":
            continue
        params[k] = v
    sorted_keys = sorted(params.keys())
    canon = "&".join(f"{_percent_encode(k)}={_percent_encode(params[k])}" for k in sorted_keys)
    string_to_sign = "GET" + "&" + _percent_encode("/") + "&" + _percent_encode(canon)
    signature = _sign(ak_secret, string_to_sign)
    params["Signature"] = signature
    return params


class AlibabaReportError(Exception):
    pass


def _call_api(ak_id: str, ak_secret: str, region: str, action: str, extra: dict, timeout=20) -> dict:
    if not ak_id or not ak_secret:
        raise AlibabaReportError("AccessKey Id / Secret tanımlı değil.")
    host = _endpoint(region)
    params = _build_signed_params(ak_id, ak_secret, action, extra)
    query = "&".join(f"{_percent_encode(k)}={_percent_encode(v)}" for k, v in params.items())
    url = f"https://{host}/?{query}"
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body = resp.read().decode("utf-8", errors="replace")
    except urllib.error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace") if exc.fp else ""
        try:
            j = json.loads(body)
            msg = j.get("Message") or j.get("message") or body
            code = j.get("Code") or j.get("code") or exc.code
        except Exception:
            msg = body or str(exc)
            code = exc.code
        raise AlibabaReportError(f"HTTP {exc.code} [{code}]: {msg}") from exc
    except Exception as exc:
        raise AlibabaReportError(f"İstek başarısız: {exc}") from exc
    try:
        data = json.loads(body)
    except Exception as exc:
        raise AlibabaReportError(f"Beklenmeyen yanıt (JSON değil): {body[:300]}") from exc
    return data


def get_config(conn) -> dict:
    ak_id = (get_mail_setting(conn, SETTING_AK_ID, "") or "").strip()
    ak_secret = (get_mail_setting(conn, SETTING_AK_SECRET, "") or "").strip()
    region = (get_mail_setting(conn, SETTING_REGION, DEFAULT_REGION) or DEFAULT_REGION).strip()
    enabled = (get_mail_setting(conn, SETTING_ENABLED, "0") or "0").strip() == "1"
    verified = (get_mail_setting(conn, SETTING_VERIFIED, "0") or "0").strip() == "1"
    last_sync = (get_mail_setting(conn, SETTING_LAST_SYNC, "") or "").strip()
    return {
        "ak_id": ak_id,
        "ak_secret": ak_secret,
        "region": region,
        "enabled": enabled,
        "verified": verified,
        "last_sync": last_sync,
        "configured": bool(ak_id and ak_secret),
    }


def save_config(conn, *, ak_id=None, ak_secret=None, region=None, enabled=None):
    if ak_id is not None:
        upsert_mail_setting(conn, SETTING_AK_ID, ak_id.strip())
    if ak_secret is not None and ak_secret.strip():
        upsert_mail_setting(conn, SETTING_AK_SECRET, ak_secret.strip())
        # Anahtar değiştiyse önceki doğrulama artık geçersiz.
        upsert_mail_setting(conn, SETTING_VERIFIED, "0")
    if region is not None:
        upsert_mail_setting(conn, SETTING_REGION, region.strip() or DEFAULT_REGION)
    if enabled is not None:
        upsert_mail_setting(conn, SETTING_ENABLED, "1" if enabled else "0")
    conn.commit()


def mask_key(k: str) -> str:
    k = (k or "").strip()
    if not k:
        return ""
    if len(k) <= 8:
        return "•" * len(k)
    return k[:4] + "•" * (len(k) - 8) + k[-4:]


def test_connection(conn) -> dict:
    """Salt-okunur, 1 kayıtlık minik bir istek — kimlik bilgisi + izin doğrulaması.
    Başarılıysa alibaba_report_verified=1 yazar (senkron job'un çalışması için şart)."""
    cfg = get_config(conn)
    if not cfg["configured"]:
        return {"ok": False, "error": "AccessKey Id / Secret girilmemiş."}
    now = datetime.now(timezone.utc)
    start = now - timedelta(days=1)
    try:
        data = _call_api(
            cfg["ak_id"], cfg["ak_secret"], cfg["region"],
            "SenderStatisticsDetailByParam",
            {
                "StartTime": start.strftime("%Y-%m-%d %H:%M"),
                "EndTime": now.strftime("%Y-%m-%d %H:%M"),
                "Length": 1,
            },
        )
    except AlibabaReportError as exc:
        return {"ok": False, "error": str(exc)}
    if "data" not in data and "Code" in data:
        return {"ok": False, "error": f"{data.get('Code')}: {data.get('Message')}"}
    upsert_mail_setting(conn, SETTING_VERIFIED, "1")
    conn.commit()
    sample = ((data.get("data") or {}).get("mailDetail") or [])
    return {
        "ok": True,
        "request_id": data.get("RequestId"),
        "sample_count": len(sample),
        "sample": sample[:1],
    }


def _match_send_id(conn, to_email: str, utc_ts, window_hours=72):
    """Bir mailDetail kaydını en yakın mail_sends satırına eşler — aynı
    e-posta için birden fazla gönderim olabileceğinden zaman farkı en
    kısa (ve zaten real_status atanmamış) satır seçilir."""
    if not to_email or not utc_ts:
        return None
    center = datetime.fromtimestamp(int(utc_ts), tz=timezone.utc)
    lo = (center - timedelta(hours=window_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    hi = (center + timedelta(hours=window_hours)).strftime("%Y-%m-%dT%H:%M:%SZ")
    rows = fetchall(
        conn,
        """
        SELECT id, created_at FROM mail_sends
        WHERE LOWER(to_email) = LOWER(?)
          AND status IN ('sent', 'simulated', 'failed', 'skipped', 'queued', 'bounced')
          AND real_status IS NULL
          AND CAST(created_at AS TEXT) >= ? AND CAST(created_at AS TEXT) <= ?
        ORDER BY id DESC
        LIMIT 20
        """,
        (to_email, lo, hi),
    ) or []
    if not rows:
        return None
    best_id, best_delta = None, None
    for r in rows:
        d = dict(r) if not isinstance(r, dict) else r
        try:
            ca = datetime.strptime((d.get("created_at") or "")[:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
        except Exception:
            continue
        delta = abs((ca - center).total_seconds())
        if best_delta is None or delta < best_delta:
            best_delta, best_id = delta, d.get("id")
    return best_id


def _mail_detail_list(payload: dict) -> list:
    """Alibaba bazen tek kaydı dict, çokluyu list döner; key de data/Data olabilir."""
    if not isinstance(payload, dict):
        return []
    block = payload.get("data") or payload.get("Data") or {}
    if isinstance(block, list):
        return [x for x in block if isinstance(x, dict)]
    if not isinstance(block, dict):
        return []
    details = block.get("mailDetail") or block.get("MailDetail") or []
    if isinstance(details, dict):
        return [details]
    if isinstance(details, list):
        return [x for x in details if isinstance(x, dict)]
    return []


def sync_delivery_reports(conn, *, hours_back=48, max_pages=8):
    """Son senkrondan bugüne (üst sınır 30 gün, Alibaba kısıtı) mailDetail
    çeker, mail_sends.real_status alanını doldurur. Sadece okuma — Alibaba
    tarafında hiçbir değişiklik yapılmaz.

    max_pages varsayılan 8: HTTP isteği Render 30s timeout'una çarpmasın
    (ilk senkron 500 Internal Server Error oluyordu). Worker periyodik
    çağrıda daha yüksek sayfa ile devam eder."""
    try:
        from database import ensure_mail_sends_real_status_columns
        ensure_mail_sends_real_status_columns(conn)
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
    cfg = get_config(conn)
    if not cfg["enabled"] or not cfg["configured"] or not cfg["verified"]:
        return {"skipped": True, "reason": "devre dışı veya doğrulanmamış"}

    now = datetime.now(timezone.utc)
    if cfg["last_sync"]:
        try:
            start = datetime.strptime(cfg["last_sync"][:19], "%Y-%m-%dT%H:%M:%S").replace(tzinfo=timezone.utc)
            start = start - timedelta(hours=2)  # az örtüşme — sınır kaçırmasın
        except Exception:
            start = now - timedelta(hours=hours_back)
    else:
        start = now - timedelta(hours=hours_back)
    start = max(start, now - timedelta(days=29))  # 30 günlük Alibaba kısıtı

    matched = 0
    seen = 0
    errors = []
    next_start = None
    pages = 0
    while pages < max_pages:
        pages += 1
        extra = {
            "StartTime": start.strftime("%Y-%m-%d %H:%M"),
            "EndTime": now.strftime("%Y-%m-%d %H:%M"),
            "Length": 100,
        }
        if next_start:
            extra["NextStart"] = next_start
        try:
            data = _call_api(cfg["ak_id"], cfg["ak_secret"], cfg["region"], "SenderStatisticsDetailByParam", extra)
        except AlibabaReportError as exc:
            errors.append(str(exc))
            break
        details = _mail_detail_list(data)
        if not details:
            break
        for d in details:
            seen += 1
            status_code = d.get("Status")
            real_status = _STATUS_MAP.get(status_code, "unknown")
            to_addr = (d.get("ToAddress") or "").strip()
            utc_ts = d.get("UtcLastUpdateTime")
            msg = d.get("Message") or d.get("ErrorClassification") or ""
            send_id = _match_send_id(conn, to_addr, utc_ts)
            if not send_id:
                continue
            try:
                when = datetime.fromtimestamp(int(utc_ts), tz=timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
            except Exception:
                when = now.strftime("%Y-%m-%dT%H:%M:%SZ")
            execute(
                conn,
                """
                UPDATE mail_sends
                SET real_status = ?, real_status_at = ?, real_status_message = ?, real_status_source = 'alibaba_api'
                WHERE id = ?
                """,
                (real_status, when, str(msg)[:500], send_id),
            )
            try:
                apply_send_outcome_to_contact(conn, send_id, real_status, msg)
            except Exception as exc:
                print(f"⚠️  alibaba outcome→contact: {exc}")
            matched += 1
        conn.commit()
        next_start = data.get("NextStart")
        if not next_start:
            break
        time.sleep(0.15)  # 500 çağrı/dk sınırına karşı nazik davran

    upsert_mail_setting(conn, SETTING_LAST_SYNC, now.strftime("%Y-%m-%dT%H:%M:%SZ"))
    conn.commit()
    dead_stamped = 0
    try:
        dead_stamped = backfill_dead_from_reports(conn, limit=4000)
    except Exception as exc:
        print(f"⚠️  alibaba dead backfill: {exc}")
    return {
        "skipped": False,
        "seen": seen,
        "matched": matched,
        "dead_stamped": dead_stamped,
        "pages": pages,
        "window_start": start.isoformat(),
        "window_end": now.isoformat(),
        "errors": errors,
    }


def real_success_rate(conn, since_ts, tenant_id=None):
    """real_status doldurulmuş kayıtlara göre GERÇEK teslimat oranı — Alibaba
    konsolündeki sayıyla birebir örtüşmesi beklenir (aynı veri kaynağı)."""
    clauses = ["CAST(created_at AS TEXT) >= ?", "real_status IS NOT NULL"]
    params = [since_ts]
    if tenant_id:
        clauses.append("tenant_id = ?")
        params.append(int(tenant_id))
    where = " AND ".join(clauses)
    try:
        delivered = int(scalar(
            conn, f"SELECT COUNT(*) FROM mail_sends WHERE {where} AND real_status = 'delivered'", tuple(params)
        ) or 0)
        total = int(scalar(conn, f"SELECT COUNT(*) FROM mail_sends WHERE {where}", tuple(params)) or 0)
    except Exception:
        return {"delivered": 0, "total": 0, "rate": None, "coverage": 0}
    rate = round(100.0 * delivered / total, 2) if total else None
    # coverage: real_status'a sahip olanların, o dönemde submit edilmiş
    # (sent/simulated/failed) toplam içindeki payı — düşükse "henüz senkronlanmadı" demek.
    try:
        submitted_clauses = ["CAST(created_at AS TEXT) >= ?", "status IN ('sent','simulated','failed')"]
        submitted_params = [since_ts]
        if tenant_id:
            submitted_clauses.append("tenant_id = ?")
            submitted_params.append(int(tenant_id))
        submitted = int(scalar(
            conn, f"SELECT COUNT(*) FROM mail_sends WHERE {' AND '.join(submitted_clauses)}",
            tuple(submitted_params),
        ) or 0)
    except Exception:
        submitted = 0
    coverage = round(100.0 * total / submitted, 1) if submitted else 0
    return {"delivered": delivered, "total": total, "rate": rate, "coverage": coverage}
