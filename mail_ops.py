"""Mailing operasyon yardımcıları — suppression, unsub, open pixel, bounce."""

from __future__ import annotations

import hashlib
import hmac
import html as html_lib
import json
import secrets
from contextlib import closing, suppress

from database import (
    execute,
    fetchall,
    fetchone,
    get_db,
    get_mail_setting,
    insert_returning_id,
    iso,
    safe_rollback,
    scalar,
    upsert_mail_setting,
    uses_postgres,
    utcnow,
)


def _ops_secret(conn=None):
    """Open/click imza anahtarı — webhook_secret ile KARIŞTIRMA (değişince tüm pixel kırılır)."""
    import os

    close = False
    if conn is None:
        conn = get_db()
        close = True
    try:
        secret = (get_mail_setting(conn, "mail_ops_secret", "") or "").strip()
        if not secret:
            secret = (os.environ.get("MAILING_SECRET_KEY") or "").strip()
        if not secret:
            secret = secrets.token_hex(24)
            upsert_mail_setting(conn, "mail_ops_secret", secret)
            try:
                conn.commit()
            except Exception:
                pass
        elif not (get_mail_setting(conn, "mail_ops_secret", "") or "").strip():
            # Env’den geldiyse DB’ye sabitle — web/worker aynı kalsın
            upsert_mail_setting(conn, "mail_ops_secret", secret)
            try:
                conn.commit()
            except Exception:
                pass
        return secret
    finally:
        if close:
            try:
                conn.close()
            except Exception:
                pass


def ensure_mail_ops_schema(conn):
    """Suppression + unsub token tabloları / kolonlar. Open secret’ı sabitle."""
    try:
        _ops_secret(conn)
    except Exception as exc:
        print(f"⚠️  mail_ops_secret ensure: {exc}")
    if uses_postgres():
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS mail_suppressions (
                email TEXT PRIMARY KEY,
                reason TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """,
        )
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS mail_unsub_tokens (
                token TEXT PRIMARY KEY,
                contact_id INTEGER,
                send_id INTEGER,
                email TEXT NOT NULL DEFAULT '',
                used_at TEXT,
                created_at TEXT NOT NULL
            )
            """,
        )
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS mail_audit_log (
                id SERIAL PRIMARY KEY,
                actor TEXT NOT NULL DEFAULT '',
                action TEXT NOT NULL DEFAULT '',
                detail TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """,
        )
    else:
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS mail_suppressions (
                email TEXT PRIMARY KEY,
                reason TEXT NOT NULL DEFAULT '',
                source TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """,
        )
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS mail_unsub_tokens (
                token TEXT PRIMARY KEY,
                contact_id INTEGER,
                send_id INTEGER,
                email TEXT NOT NULL DEFAULT '',
                used_at TEXT,
                created_at TEXT NOT NULL
            )
            """,
        )
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS mail_audit_log (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                actor TEXT NOT NULL DEFAULT '',
                action TEXT NOT NULL DEFAULT '',
                detail TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """,
        )
    execute(conn, "CREATE INDEX IF NOT EXISTS idx_mail_suppressions_reason ON mail_suppressions(reason)")
    execute(conn, "CREATE INDEX IF NOT EXISTS idx_mail_unsub_email ON mail_unsub_tokens(email)")
    # contact consent
    try:
        from database import _table_columns
        cols = _table_columns(conn, "mail_contacts") or set()
        if cols and "consent_source" not in cols:
            execute(conn, "ALTER TABLE mail_contacts ADD COLUMN consent_source TEXT NOT NULL DEFAULT ''")
        if cols and "consented_at" not in cols:
            execute(conn, "ALTER TABLE mail_contacts ADD COLUMN consented_at TEXT")
        dcols = _table_columns(conn, "mail_domains") or set()
        if dcols and "rate_per_minute" not in dcols:
            execute(conn, "ALTER TABLE mail_domains ADD COLUMN rate_per_minute INTEGER NOT NULL DEFAULT 0")
    except Exception:
        try:
            conn.rollback()
        except Exception:
            pass
    try:
        conn.commit()
    except Exception:
        pass


def audit(conn, actor, action, detail=""):
    try:
        execute(
            conn,
            "INSERT INTO mail_audit_log (actor, action, detail, created_at) VALUES (?, ?, ?, ?)",
            ((actor or "")[:120], (action or "")[:120], (detail or "")[:2000], iso(utcnow())),
        )
    except Exception:
        pass


def is_suppressed(conn, email):
    email = (email or "").strip().lower()
    if not email:
        return True
    row = fetchone(conn, "SELECT email FROM mail_suppressions WHERE email = ?", (email,))
    if row:
        return True
    c = fetchone(conn, "SELECT unsubscribed FROM mail_contacts WHERE LOWER(email) = ?", (email,))
    if c and int(c["unsubscribed"] or 0):
        return True
    return False


def suppress_email(conn, email, reason="unsubscribed", source="system"):
    email = (email or "").strip().lower()
    if not email:
        return
    now = iso(utcnow())
    if uses_postgres():
        try:
            execute(
                conn,
                """
                INSERT INTO mail_suppressions (email, reason, source, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT (email) DO UPDATE SET reason = EXCLUDED.reason, source = EXCLUDED.source
                """,
                (email, reason, source, now),
            )
        except Exception:
            # UNIQUE(email) yoksa / conflict hedefi tutmazsa fallback
            with suppress(Exception):
                conn.rollback()
            existing = fetchone(conn, "SELECT email FROM mail_suppressions WHERE email = ?", (email,))
            if existing:
                execute(
                    conn,
                    "UPDATE mail_suppressions SET reason = ?, source = ? WHERE email = ?",
                    (reason, source, email),
                )
            else:
                execute(
                    conn,
                    "INSERT INTO mail_suppressions (email, reason, source, created_at) VALUES (?, ?, ?, ?)",
                    (email, reason, source, now),
                )
    else:
        execute(
            conn,
            "INSERT OR REPLACE INTO mail_suppressions (email, reason, source, created_at) VALUES (?, ?, ?, ?)",
            (email, reason, source, now),
        )
    execute(
        conn,
        "UPDATE mail_contacts SET unsubscribed = 1, updated_at = ? WHERE LOWER(email) = ?",
        (now, email),
    )


def make_unsub_token(conn, *, email, contact_id=None, send_id=None):
    token = secrets.token_urlsafe(18)
    sp = "sp_mail_unsub"
    try:
        if uses_postgres():
            execute(conn, f"SAVEPOINT {sp}")
        execute(
            conn,
            """
            INSERT INTO mail_unsub_tokens (token, contact_id, send_id, email, used_at, created_at)
            VALUES (?, ?, ?, ?, NULL, ?)
            """,
            (token, contact_id, send_id, (email or "").strip().lower(), iso(utcnow())),
        )
        if uses_postgres():
            execute(conn, f"RELEASE SAVEPOINT {sp}")
    except Exception as exc:
        print(f"⚠️  mail_unsub_tokens insert: {exc}")
        try:
            if uses_postgres():
                execute(conn, f"ROLLBACK TO SAVEPOINT {sp}")
            else:
                safe_rollback(conn)
        except Exception:
            safe_rollback(conn)
    return token


def unsub_url(token):
    from mailing_routes import _public_base
    return f"{_public_base()}/m/u/{token}"


def open_url(send_id, conn=None):
    from mailing_routes import _public_base
    close = False
    if conn is None:
        conn = get_db()
        close = True
    try:
        secret = _ops_secret(conn)
        sig = hmac.new(secret.encode(), f"open:{int(send_id)}".encode(), hashlib.sha256).hexdigest()[:20]
        return f"{_public_base()}/m/o/{int(send_id)}/{sig}"
    finally:
        if close:
            try:
                conn.close()
            except Exception:
                pass


def verify_open_sig(conn, send_id, sig):
    """İmza doğrula — yeni mail_ops_secret + eski webhook_secret (geçiş)."""
    got = (sig or "").strip()
    if not got:
        return False
    secret = _ops_secret(conn)
    expect = hmac.new(secret.encode(), f"open:{int(send_id)}".encode(), hashlib.sha256).hexdigest()[:20]
    if hmac.compare_digest(expect, got):
        return True
    # Eski mailler webhook_secret ile imzalanmış olabilir
    try:
        legacy = (get_mail_setting(conn, "webhook_secret", "") or "").strip()
        if legacy and legacy != secret:
            expect2 = hmac.new(
                legacy.encode(), f"open:{int(send_id)}".encode(), hashlib.sha256
            ).hexdigest()[:20]
            if hmac.compare_digest(expect2, got):
                return True
    except Exception:
        pass
    return False


def apply_unsubscribe(conn, token):
    token = (token or "").strip()
    row = fetchone(conn, "SELECT * FROM mail_unsub_tokens WHERE token = ?", (token,))
    if not row:
        return False, "Geçersiz bağlantı"
    row = dict(row)
    email = (row.get("email") or "").strip().lower()
    if row.get("used_at"):
        return True, email or "ok"
    now = iso(utcnow())
    if email:
        suppress_email(conn, email, reason="unsubscribed", source="link")
    if row.get("contact_id"):
        execute(
            conn,
            "UPDATE mail_contacts SET unsubscribed = 1, updated_at = ? WHERE id = ?",
            (now, row["contact_id"]),
        )
    execute(conn, "UPDATE mail_unsub_tokens SET used_at = ? WHERE token = ?", (now, token))
    return True, email


def record_open(conn, send_id):
    now = iso(utcnow())
    row = fetchone(
        conn,
        "SELECT id, opened_at, clicked_at, contact_id FROM mail_sends WHERE id = ?",
        (int(send_id),),
    )
    if not row:
        return False
    if not row.get("opened_at"):
        execute(conn, "UPDATE mail_sends SET opened_at = ? WHERE id = ?", (now, send_id))
        if row.get("contact_id"):
            try:
                from mailing_routes import _tag_contact
                cid = row["contact_id"]
                _tag_contact(conn, cid, "mail_acan", now)
                # Açıp tıklayan havuzu — daha önce tıklamışsa
                if row.get("clicked_at"):
                    _tag_contact(conn, cid, "mail_tiklayan", now)
                    _tag_contact(conn, cid, "mail_acan_tiklayan", now)
            except Exception:
                pass
    return True


def tag_send_outcome(conn, contact_id, status, now=None):
    """Gönderim sonucu otomatik etiket havuzları."""
    if not contact_id:
        return
    now = now or iso(utcnow())
    try:
        from mailing_routes import _tag_contact
        st = (status or "").strip().lower()
        if st in ("sent", "simulated", "queued"):
            _tag_contact(conn, contact_id, "mail_gonderilen", now)
        elif st in ("failed", "bounced", "error"):
            _tag_contact(conn, contact_id, "mail_hata", now)
    except Exception:
        pass


def tag_click_outcome(conn, contact_id, *, opened=False, now=None):
    if not contact_id:
        return
    now = now or iso(utcnow())
    try:
        from mailing_routes import _tag_contact
        _tag_contact(conn, contact_id, "mail_tiklayan", now)
        if opened:
            _tag_contact(conn, contact_id, "mail_acan", now)
            _tag_contact(conn, contact_id, "mail_acan_tiklayan", now)
    except Exception:
        pass


def inject_ops_footer(conn, body, *, send_id, contact_id=None, email="", as_html=True):
    """Open pixel + List-Unsubscribe URL + şablon bozmayan discreete unsub.

    Şablon HTML'ine dokunulmaz — gönderim anında eklenir.
    Pixel hem <body> hemen sonrası hem sonda (istemci/proxy güvenilirliği).
    Dönüş: (body, unsub_url).
    """
    import re

    body = body or ""
    email = (email or "").strip().lower()
    token = make_unsub_token(conn, email=email, contact_id=contact_id, send_id=send_id)
    uurl = unsub_url(token)
    opixel = open_url(send_id, conn)
    href = html_lib.escape(uurl, quote=True)
    if as_html:
        pixel_src = html_lib.escape(opixel, quote=True)
        pixel = (
            f'<img src="{pixel_src}" width="1" height="1" alt="" '
            'data-mm-ops-open="1" '
            'style="display:block;width:1px;height:1px;border:0;outline:none;" />'
        )
        has_unsub = 'data-mm-ops-unsub="1"' in body or "data-mm-ops-unsub='1'" in body
        has_open = 'data-mm-ops-open="1"' in body or "data-mm-ops-open='1'" in body
        discreet = ""
        if not has_unsub:
            discreet = (
                '<div data-mm-ops-unsub="1" style="margin:18px 0 0;padding:0;text-align:center;'
                'font-family:Arial,Helvetica,sans-serif;line-height:1.2;">'
                f'<a href="{href}" target="_blank" rel="noopener noreferrer" '
                'style="color:#9ca3af;font-size:9px;font-weight:400;text-decoration:underline;'
                'letter-spacing:0;">Abonelikten çık</a>'
                "</div>"
            )
        # Açılma pikseli yoksa mutlaka ekle (eski kod unsub varken pixel’i de atlıyordu)
        if not has_open:
            # Üst: bazı istemciler sadece yukarıyı yükler
            if re.search(r"(?i)<body[^>]*>", body):
                body = re.sub(
                    r"(?i)(<body[^>]*>)",
                    r"\1" + pixel,
                    body,
                    count=1,
                )
            footer = discreet + pixel
            if re.search(r"(?i)</body>", body):
                body = re.sub(r"(?i)</body>", footer + "</body>", body, count=1)
            else:
                body = body + footer
        elif discreet:
            if re.search(r"(?i)</body>", body):
                body = re.sub(r"(?i)</body>", discreet + "</body>", body, count=1)
            else:
                body = body + discreet
        return body, uurl
    if "Abonelikten çık:" in (body or ""):
        return body, uurl
    return (body or "") + f"\n\nAbonelikten çık: {uurl}\n", uurl


def list_unsubscribe_headers(unsub_http_url):
    """RFC 2369 List-Unsubscribe header değerleri."""
    return {
        "List-Unsubscribe": f"<{unsub_http_url}>",
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
    }


def _empty_sc_metrics():
    return {
        "sc_register": 0,
        "sc_deposit_total": 0.0,
        "sc_ftd_count": 0,
        "sc_ftd_total": 0.0,
        "sc_withdraw_total": 0.0,
        "sc_bonus_total": 0.0,
    }


def _smartico_by_contact(conn):
    """contact_id (afp1/subid) → smartico player metrics. Hata olursa {}."""
    try:
        import smartico_api
        from database import get_mail_setting

        affiliate_id = (get_mail_setting(conn, "smartico_affiliate_id", "") or "").strip()
        subid_param = (get_mail_setting(conn, "smartico_subid_param", "afp1") or "afp1").strip() or "afp1"
        if not affiliate_id or not smartico_api.is_configured(conn):
            return {}
        result = smartico_api.fetch_mailing_players(
            conn, affiliate_id, subid_param, period="6months", force=False,
        )
        out = {}
        for row in result.get("rows") or []:
            sid = str(row.get("subid") or "").strip()
            if not sid:
                continue
            try:
                out[int(sid)] = row
            except (TypeError, ValueError):
                continue
        return out
    except Exception:
        return {}


def campaign_analytics(conn, campaign_id=None):
    """Kampanya bazlı open/click/fail + Smartico (register/yatırım/FTD/çekim/bonus)."""
    params = []
    where = ""
    if campaign_id:
        where = "WHERE c.id = ?"
        params.append(int(campaign_id))
    rows = fetchall(
        conn,
        f"""
        SELECT
            c.id,
            c.name,
            c.status,
            c.error,
            c.domain_id,
            COALESCE(c.sent_count, 0) AS sent_count,
            COALESCE(c.failed_count, 0) AS failed_count,
            COALESCE(c.skipped_count, 0) AS skipped_count,
            COALESCE(c.total_count, 0) AS total_count,
            (SELECT COUNT(*) FROM mail_sends s
             WHERE s.campaign_id = c.id AND s.opened_at IS NOT NULL) AS opened,
            (SELECT COUNT(*) FROM mail_sends s
             WHERE s.campaign_id = c.id AND s.clicked_at IS NOT NULL) AS clicked,
            (SELECT COUNT(*) FROM mail_sends s
             WHERE s.campaign_id = c.id AND s.status IN ('sent','simulated')) AS delivered,
            (SELECT COUNT(*) FROM mail_sends s
             WHERE s.campaign_id = c.id AND s.status = 'sent') AS delivered_real,
            (SELECT COUNT(*) FROM mail_sends s
             WHERE s.campaign_id = c.id AND s.status = 'simulated') AS delivered_simulated
        FROM mail_campaigns c
        {where}
        ORDER BY c.id DESC
        LIMIT 50
        """,
        tuple(params),
    )
    sc_map = _smartico_by_contact(conn)
    out = []
    for r in rows or []:
        d = dict(r)
        real_n = int(d.get("delivered_real") or 0)
        sim_n = int(d.get("delivered_simulated") or 0)
        if real_n and sim_n:
            d["delivery_kind"] = "mixed"
        elif real_n:
            d["delivery_kind"] = "real"
        elif sim_n:
            d["delivery_kind"] = "simulated"
        else:
            d["delivery_kind"] = "none"
        # Tıklama: mail_sends.clicked_at ∪ mail_click_links (eski / yeni)
        clicked = int(d.get("clicked") or 0)
        try:
            link_clicks = int(
                scalar(
                    conn,
                    """
                    SELECT COUNT(DISTINCT send_id) FROM mail_click_links
                    WHERE campaign_id = ?
                      AND send_id IS NOT NULL
                      AND COALESCE(click_count, 0) > 0
                    """,
                    (d["id"],),
                )
                or 0
            )
            if link_clicks > clicked:
                clicked = link_clicks
                d["clicked"] = clicked
        except Exception:
            safe_rollback(conn)
        # Alıcı / gönderim sapması
        try:
            recip = int(
                scalar(
                    conn,
                    "SELECT COUNT(*) FROM mail_campaign_recipients WHERE campaign_id = ?",
                    (d["id"],),
                )
                or 0
            )
            uniq_emails = int(
                scalar(
                    conn,
                    """
                    SELECT COUNT(*) FROM (
                      SELECT LOWER(to_email) AS e FROM mail_sends
                      WHERE campaign_id = ? AND status IN ('sent','simulated')
                      GROUP BY LOWER(to_email)
                    ) t
                    """,
                    (d["id"],),
                )
                or 0
            )
            send_rows = int(
                scalar(
                    conn,
                    """
                    SELECT COUNT(*) FROM mail_sends
                    WHERE campaign_id = ? AND status IN ('sent','simulated')
                    """,
                    (d["id"],),
                )
                or 0
            )
            d["recipient_count"] = recip
            d["unique_delivered"] = uniq_emails
            d["oversend"] = bool(send_rows > recip and recip > 0)
            d["dup_sends"] = max(0, send_rows - uniq_emails)
        except Exception:
            safe_rollback(conn)
            d["recipient_count"] = int(d.get("total_count") or 0)
            d["unique_delivered"] = int(d.get("delivered") or 0)
            d["oversend"] = False
            d["dup_sends"] = 0

        delivered = int(d.get("delivered") or 0) or 1
        d["open_rate"] = round(100.0 * int(d.get("opened") or 0) / delivered, 2)
        d["click_rate"] = round(100.0 * clicked / delivered, 2)
        d["clicked"] = clicked
        d["error"] = (d.get("error") or "") or ""
        sc = _empty_sc_metrics()
        try:
            cid_rows = fetchall(
                conn,
                """
                SELECT DISTINCT contact_id FROM mail_click_links
                WHERE campaign_id = ? AND is_smartico = 1 AND contact_id IS NOT NULL
                """,
                (d["id"],),
            ) or []
        except Exception:
            safe_rollback(conn)
            cid_rows = []
        seen = set()
        for cr in cid_rows:
            try:
                cid = int(cr["contact_id"])
            except (TypeError, ValueError, KeyError):
                continue
            if cid in seen:
                continue
            seen.add(cid)
            p = sc_map.get(cid)
            if not p:
                continue
            sc["sc_register"] += max(int(p.get("registration_count") or 0), 1)
            sc["sc_deposit_total"] += float(p.get("deposit_total") or 0)
            sc["sc_ftd_count"] += int(p.get("ftd_count") or 0)
            sc["sc_ftd_total"] += float(p.get("ftd_total") or 0)
            sc["sc_withdraw_total"] += float(p.get("withdrawal_total") or 0)
            sc["sc_bonus_total"] += float(p.get("bonus_total") or 0)
        for k in ("sc_deposit_total", "sc_ftd_total", "sc_withdraw_total", "sc_bonus_total"):
            sc[k] = round(sc[k], 2)
        d.update(sc)
        out.append(d)
    return out


def smartico_dashboard_summary(conn):
    """Dashboard kartları için Smartico özet (30 gün)."""
    empty = {
        "register": 0,
        "deposit_total": 0.0,
        "ftd_count": 0,
        "ftd_total": 0.0,
        "withdraw_total": 0.0,
        "bonus_total": 0.0,
        "currency": "",
        "error": None,
    }
    try:
        import smartico_api
        from database import get_mail_setting

        affiliate_id = (get_mail_setting(conn, "smartico_affiliate_id", "") or "").strip()
        subid_param = (get_mail_setting(conn, "smartico_subid_param", "afp1") or "afp1").strip() or "afp1"
        if not affiliate_id or not smartico_api.is_configured(conn):
            empty["error"] = "not_configured"
            return empty
        result = smartico_api.fetch_mailing_players(
            conn, affiliate_id, subid_param, period="30days", force=False,
        )
        if result.get("error") and not result.get("rows"):
            empty["error"] = result.get("error")
            return empty
        s = result.get("summary") or {}
        return {
            "register": int(s.get("registration_count") or 0),
            "deposit_total": float(s.get("deposit_total") or 0),
            "ftd_count": int(s.get("ftd_count") or 0),
            "ftd_total": float(s.get("ftd_total") or 0),
            "withdraw_total": float(s.get("withdrawal_total") or 0),
            "bonus_total": float(s.get("bonus_total") or 0),
            "currency": result.get("currency") or "",
            "error": None,
            "source": result.get("source"),
        }
    except Exception as exc:
        empty["error"] = str(exc)
        return empty
