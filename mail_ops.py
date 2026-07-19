"""Mailing operasyon yardımcıları — suppression, unsub, open pixel, bounce."""

from __future__ import annotations

import hashlib
import hmac
import html as html_lib
import json
import secrets
from contextlib import closing

from database import (
    execute,
    fetchall,
    fetchone,
    get_db,
    get_mail_setting,
    insert_returning_id,
    iso,
    scalar,
    upsert_mail_setting,
    uses_postgres,
    utcnow,
)


def _ops_secret(conn=None):
    close = False
    if conn is None:
        conn = get_db()
        close = True
    try:
        secret = (get_mail_setting(conn, "webhook_secret", "") or "").strip()
        if not secret:
            secret = (get_mail_setting(conn, "mail_ops_secret", "") or "").strip()
        if not secret:
            secret = secrets.token_hex(24)
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
    """Suppression + unsub token tabloları / kolonlar."""
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
        execute(
            conn,
            """
            INSERT INTO mail_suppressions (email, reason, source, created_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT (email) DO UPDATE SET reason = EXCLUDED.reason, source = EXCLUDED.source
            """,
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
    execute(
        conn,
        """
        INSERT INTO mail_unsub_tokens (token, contact_id, send_id, email, used_at, created_at)
        VALUES (?, ?, ?, ?, NULL, ?)
        """,
        (token, contact_id, send_id, (email or "").strip().lower(), iso(utcnow())),
    )
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
    secret = _ops_secret(conn)
    expect = hmac.new(secret.encode(), f"open:{int(send_id)}".encode(), hashlib.sha256).hexdigest()[:20]
    return hmac.compare_digest(expect, (sig or "").strip())


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
    row = fetchone(conn, "SELECT id, opened_at, contact_id FROM mail_sends WHERE id = ?", (int(send_id),))
    if not row:
        return False
    if not row.get("opened_at"):
        execute(conn, "UPDATE mail_sends SET opened_at = ? WHERE id = ?", (now, send_id))
        if row.get("contact_id"):
            try:
                from mailing_routes import _tag_contact
                _tag_contact(conn, row["contact_id"], "mail_acan", now)
            except Exception:
                pass
    return True


def inject_ops_footer(conn, body, *, send_id, contact_id=None, email="", as_html=True):
    """Open pixel + unsubscribe footer. Dönüş: (body, unsub_url)."""
    import re

    body = body or ""
    email = (email or "").strip().lower()
    token = make_unsub_token(conn, email=email, contact_id=contact_id, send_id=send_id)
    uurl = unsub_url(token)
    opixel = open_url(send_id, conn)
    if as_html:
        footer = (
            '<div style="margin-top:24px;padding-top:12px;border-top:1px solid #e5e7eb;'
            'font-size:12px;color:#6b7280;line-height:1.5;">'
            f'<a href="{html_lib.escape(uurl, quote=True)}" style="color:#6b7280;">'
            "Abonelikten çık / Unsubscribe</a>"
            f'<img src="{html_lib.escape(opixel, quote=True)}" width="1" height="1" alt="" '
            'style="display:block;width:1px;height:1px;border:0;" />'
            "</div>"
        )
        if re.search(r"(?i)</body>", body):
            body = re.sub(r"(?i)</body>", footer + "</body>", body, count=1)
        else:
            body = body + footer
        return body, uurl
    footer = f"\n\n---\nAbonelikten çık: {uurl}\n"
    return body + footer, uurl


def list_unsubscribe_headers(unsub_http_url):
    """RFC 2369 List-Unsubscribe header değerleri."""
    return {
        "List-Unsubscribe": f"<{unsub_http_url}>",
        "List-Unsubscribe-Post": "List-Unsubscribe=One-Click",
    }


def campaign_analytics(conn, campaign_id=None):
    """Kampanya bazlı open/click/fail oranları."""
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
             WHERE s.campaign_id = c.id AND s.status IN ('sent','simulated')) AS delivered
        FROM mail_campaigns c
        {where}
        ORDER BY c.id DESC
        LIMIT 50
        """,
        tuple(params),
    )
    out = []
    for r in rows or []:
        d = dict(r)
        delivered = int(d.get("delivered") or 0) or 1
        d["open_rate"] = round(100.0 * int(d.get("opened") or 0) / delivered, 2)
        d["click_rate"] = round(100.0 * int(d.get("clicked") or 0) / delivered, 2)
        out.append(d)
    return out
