"""Mailing modülü API rotaları — CRM, şablon, kampanya, IVR, rapor iskeleti."""

from __future__ import annotations

import csv
import io
import json
import re
import secrets
from contextlib import closing

from flask import Blueprint, jsonify, request

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
    utcnow,
)

MODULE_ACCESS = ("module.mailing",)
MAIL_DASH = ("mailing.dashboard", "module.mailing")
MAIL_CRM = ("mailing.crm", "module.mailing")
MAIL_TPL = ("mailing.templates", "module.mailing")
MAIL_CAMP = ("mailing.campaigns", "module.mailing")
MAIL_IVR = ("mailing.ivr", "module.mailing")
MAIL_REP = ("mailing.reports", "module.mailing")
MAIL_SET = ("mailing.settings", "module.mailing")

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def _row(r):
    if not r:
        return None
    return dict(r)


def _rows(rs):
    return [dict(r) for r in (rs or [])]


def _parse_tags(raw):
    if raw is None:
        return []
    if isinstance(raw, list):
        return [str(t).strip() for t in raw if str(t).strip()]
    if isinstance(raw, str):
        raw = raw.strip()
        if not raw:
            return []
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return [str(t).strip() for t in data if str(t).strip()]
        except Exception:
            pass
        return [t.strip() for t in raw.split(",") if t.strip()]
    return []


def _tags_json(tags):
    return json.dumps(_parse_tags(tags), ensure_ascii=False)


def _contact_out(row):
    d = _row(row)
    if not d:
        return None
    d["tags"] = _parse_tags(d.get("tags"))
    d["unsubscribed"] = bool(d.get("unsubscribed"))
    return d


def _render_template(text, contact):
    text = text or ""
    mapping = {
        "name": (contact or {}).get("name") or "",
        "email": (contact or {}).get("email") or "",
        "phone": (contact or {}).get("phone") or "",
    }
    for key, val in mapping.items():
        text = text.replace("{{" + key + "}}", str(val))
    return text


def _stub_send(conn, *, channel, to_email, subject, contact=None, campaign_id=None,
               contact_id=None, template_id=None, domain_id=None, to_phone=""):
    """Alibaba bağlanana kadar simüle gönderim kaydı oluşturur."""
    now = iso(utcnow())
    mode = (get_mail_setting(conn, "provider_mode", "stub") or "stub").strip().lower()
    status = "simulated" if mode == "stub" else "queued"
    msg_id = f"stub-{secrets.token_hex(8)}" if status == "simulated" else ""
    send_id = insert_returning_id(
        conn,
        """
        INSERT INTO mail_sends (
            channel, campaign_id, contact_id, template_id, domain_id,
            to_email, to_phone, subject, status, provider_msg_id, error,
            opened_at, clicked_at, sent_at, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            channel,
            campaign_id,
            contact_id,
            template_id,
            domain_id,
            to_email,
            to_phone or "",
            subject or "",
            status,
            msg_id,
            "" if status == "simulated" else "Provider henüz bağlanmadı (stub kuyruk)",
            None,
            None,
            now if status == "simulated" else None,
            now,
        ),
    )
    return send_id, status


def create_mailing_blueprint(permission_required):
    bp = Blueprint("mailing", __name__, url_prefix="/api/mailing")

    def mail_perm(*keys):
        return permission_required(*keys)

    # ── Dashboard ──────────────────────────────────────────────
    @bp.route("/dashboard", methods=["GET"])
    @mail_perm(*MAIL_DASH)
    def dashboard():
        with closing(get_db()) as conn:
            contacts = scalar(conn, "SELECT COUNT(*) FROM mail_contacts") or 0
            active_contacts = scalar(
                conn, "SELECT COUNT(*) FROM mail_contacts WHERE unsubscribed = 0"
            ) or 0
            templates = scalar(conn, "SELECT COUNT(*) FROM mail_templates") or 0
            campaigns = scalar(conn, "SELECT COUNT(*) FROM mail_campaigns") or 0
            sends_total = scalar(conn, "SELECT COUNT(*) FROM mail_sends") or 0
            sends_sim = scalar(
                conn, "SELECT COUNT(*) FROM mail_sends WHERE status IN ('simulated','sent')"
            ) or 0
            sends_queued = scalar(
                conn, "SELECT COUNT(*) FROM mail_sends WHERE status = 'queued'"
            ) or 0
            sends_failed = scalar(
                conn, "SELECT COUNT(*) FROM mail_sends WHERE status = 'failed'"
            ) or 0
            opened = scalar(
                conn, "SELECT COUNT(*) FROM mail_sends WHERE opened_at IS NOT NULL"
            ) or 0
            clicked = scalar(
                conn, "SELECT COUNT(*) FROM mail_sends WHERE clicked_at IS NOT NULL"
            ) or 0
            ivr_events = scalar(conn, "SELECT COUNT(*) FROM mail_ivr_events") or 0
            domains = _rows(fetchall(conn, "SELECT * FROM mail_domains ORDER BY id ASC"))
            provider = get_mail_setting(conn, "provider_mode", "stub")
        return jsonify({
            "kpi": {
                "contacts": contacts,
                "active_contacts": active_contacts,
                "templates": templates,
                "campaigns": campaigns,
                "sends_total": sends_total,
                "sends_delivered": sends_sim,
                "sends_queued": sends_queued,
                "sends_failed": sends_failed,
                "opened": opened,
                "clicked": clicked,
                "ivr_events": ivr_events,
            },
            "domains": domains,
            "provider_mode": provider,
            "note": "Gönderim şu an stub modunda; Alibaba DirectMail bağlanınca gerçek iletime geçer.",
        })

    # ── Contacts / CRM ─────────────────────────────────────────
    @bp.route("/contacts", methods=["GET"])
    @mail_perm(*MAIL_CRM)
    def list_contacts():
        q = (request.args.get("q") or "").strip().lower()
        tag = (request.args.get("tag") or "").strip()
        limit = min(int(request.args.get("limit") or 200), 1000)
        with closing(get_db()) as conn:
            rows = _rows(fetchall(
                conn,
                "SELECT * FROM mail_contacts ORDER BY id DESC LIMIT ?",
                (limit,),
            ))
        out = []
        for r in rows:
            c = _contact_out(r)
            if q:
                blob = f"{c.get('email','')} {c.get('name','')} {c.get('phone','')}".lower()
                if q not in blob:
                    continue
            if tag and tag not in (c.get("tags") or []):
                continue
            out.append(c)
        return jsonify({"contacts": out, "count": len(out)})

    @bp.route("/contacts", methods=["POST"])
    @mail_perm(*MAIL_CRM)
    def create_contact():
        data = request.get_json(silent=True) or {}
        email = (data.get("email") or "").strip().lower()
        if not email or not EMAIL_RE.match(email):
            return jsonify({"error": "Geçerli bir e-posta girin."}), 400
        now = iso(utcnow())
        tags = _tags_json(data.get("tags"))
        with closing(get_db()) as conn:
            existing = fetchone(conn, "SELECT id FROM mail_contacts WHERE LOWER(email) = ?", (email,))
            if existing:
                return jsonify({"error": "Bu e-posta zaten kayıtlı.", "id": existing["id"]}), 409
            cid = insert_returning_id(
                conn,
                """
                INSERT INTO mail_contacts
                (email, phone, name, tags, source, unsubscribed, notes, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    email,
                    (data.get("phone") or "").strip(),
                    (data.get("name") or "").strip(),
                    tags,
                    (data.get("source") or "manual").strip() or "manual",
                    1 if data.get("unsubscribed") else 0,
                    (data.get("notes") or "").strip(),
                    now,
                    now,
                ),
            )
            for t in _parse_tags(data.get("tags")):
                _ensure_tag(conn, t, now)
            conn.commit()
            row = fetchone(conn, "SELECT * FROM mail_contacts WHERE id = ?", (cid,))
        return jsonify({"contact": _contact_out(row)}), 201

    @bp.route("/contacts/<int:contact_id>", methods=["PATCH"])
    @mail_perm(*MAIL_CRM)
    def update_contact(contact_id):
        data = request.get_json(silent=True) or {}
        now = iso(utcnow())
        with closing(get_db()) as conn:
            row = fetchone(conn, "SELECT * FROM mail_contacts WHERE id = ?", (contact_id,))
            if not row:
                return jsonify({"error": "Kontak bulunamadı."}), 404
            email = (data.get("email") if "email" in data else row["email"] or "").strip().lower()
            if not email or not EMAIL_RE.match(email):
                return jsonify({"error": "Geçerli bir e-posta girin."}), 400
            tags = _tags_json(data.get("tags")) if "tags" in data else row["tags"]
            execute(
                conn,
                """
                UPDATE mail_contacts SET
                    email = ?, phone = ?, name = ?, tags = ?, source = ?,
                    unsubscribed = ?, notes = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    email,
                    (data.get("phone") if "phone" in data else row["phone"] or "").strip(),
                    (data.get("name") if "name" in data else row["name"] or "").strip(),
                    tags,
                    (data.get("source") if "source" in data else row["source"] or "manual").strip(),
                    1 if data.get("unsubscribed", row["unsubscribed"]) else 0,
                    (data.get("notes") if "notes" in data else row["notes"] or "").strip(),
                    now,
                    contact_id,
                ),
            )
            if "tags" in data:
                for t in _parse_tags(data.get("tags")):
                    _ensure_tag(conn, t, now)
            conn.commit()
            row = fetchone(conn, "SELECT * FROM mail_contacts WHERE id = ?", (contact_id,))
        return jsonify({"contact": _contact_out(row)})

    @bp.route("/contacts/<int:contact_id>", methods=["DELETE"])
    @mail_perm(*MAIL_CRM)
    def delete_contact(contact_id):
        with closing(get_db()) as conn:
            execute(conn, "DELETE FROM mail_contacts WHERE id = ?", (contact_id,))
            conn.commit()
        return jsonify({"ok": True})

    @bp.route("/contacts/import", methods=["POST"])
    @mail_perm(*MAIL_CRM)
    def import_contacts():
        data = request.get_json(silent=True) or {}
        raw_csv = data.get("csv") or ""
        default_tag = (data.get("tag") or "").strip()
        if not raw_csv.strip():
            return jsonify({"error": "CSV içeriği boş."}), 400
        reader = csv.DictReader(io.StringIO(raw_csv))
        now = iso(utcnow())
        created = 0
        updated = 0
        skipped = 0
        with closing(get_db()) as conn:
            for row in reader:
                email = (row.get("email") or row.get("Email") or row.get("EMAIL") or "").strip().lower()
                if not email or not EMAIL_RE.match(email):
                    skipped += 1
                    continue
                name = (row.get("name") or row.get("Name") or "").strip()
                phone = (row.get("phone") or row.get("Phone") or row.get("tel") or "").strip()
                tags = _parse_tags(row.get("tags") or row.get("tag") or "")
                if default_tag and default_tag not in tags:
                    tags.append(default_tag)
                existing = fetchone(conn, "SELECT id, tags FROM mail_contacts WHERE LOWER(email) = ?", (email,))
                if existing:
                    merged = list(dict.fromkeys(_parse_tags(existing["tags"]) + tags))
                    execute(
                        conn,
                        """
                        UPDATE mail_contacts SET name = COALESCE(NULLIF(?, ''), name),
                            phone = COALESCE(NULLIF(?, ''), phone),
                            tags = ?, updated_at = ?
                        WHERE id = ?
                        """,
                        (name, phone, _tags_json(merged), now, existing["id"]),
                    )
                    updated += 1
                else:
                    insert_returning_id(
                        conn,
                        """
                        INSERT INTO mail_contacts
                        (email, phone, name, tags, source, unsubscribed, notes, created_at, updated_at)
                        VALUES (?, ?, ?, ?, ?, 0, '', ?, ?)
                        """,
                        (email, phone, name, _tags_json(tags), "csv", now, now),
                    )
                    created += 1
                for t in tags:
                    _ensure_tag(conn, t, now)
            conn.commit()
        return jsonify({"created": created, "updated": updated, "skipped": skipped})

    def _ensure_tag(conn, name, now):
        name = (name or "").strip()
        if not name:
            return
        exists = scalar(conn, "SELECT COUNT(*) FROM mail_contact_tags WHERE name = ?", (name,))
        if not exists:
            insert_returning_id(
                conn,
                "INSERT INTO mail_contact_tags (name, created_at) VALUES (?, ?)",
                (name, now),
            )

    @bp.route("/tags", methods=["GET"])
    @mail_perm(*MAIL_CRM)
    def list_tags():
        with closing(get_db()) as conn:
            rows = _rows(fetchall(conn, "SELECT * FROM mail_contact_tags ORDER BY name ASC"))
        return jsonify({"tags": rows})

    @bp.route("/tags", methods=["POST"])
    @mail_perm(*MAIL_CRM)
    def create_tag():
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"error": "Etiket adı gerekli."}), 400
        now = iso(utcnow())
        with closing(get_db()) as conn:
            _ensure_tag(conn, name, now)
            conn.commit()
            row = fetchone(conn, "SELECT * FROM mail_contact_tags WHERE name = ?", (name,))
        return jsonify({"tag": _row(row)}), 201

    # ── Templates ──────────────────────────────────────────────
    @bp.route("/templates", methods=["GET"])
    @mail_perm(*MAIL_TPL)
    def list_templates():
        with closing(get_db()) as conn:
            rows = _rows(fetchall(conn, "SELECT * FROM mail_templates ORDER BY id DESC"))
        return jsonify({"templates": rows})

    @bp.route("/templates", methods=["POST"])
    @mail_perm(*MAIL_TPL)
    def create_template():
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"error": "Şablon adı gerekli."}), 400
        now = iso(utcnow())
        with closing(get_db()) as conn:
            tid = insert_returning_id(
                conn,
                """
                INSERT INTO mail_templates (name, subject, html_body, text_body, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    name,
                    (data.get("subject") or "").strip(),
                    data.get("html_body") or "",
                    data.get("text_body") or "",
                    now,
                    now,
                ),
            )
            conn.commit()
            row = fetchone(conn, "SELECT * FROM mail_templates WHERE id = ?", (tid,))
        return jsonify({"template": _row(row)}), 201

    @bp.route("/templates/<int:template_id>", methods=["PATCH"])
    @mail_perm(*MAIL_TPL)
    def update_template(template_id):
        data = request.get_json(silent=True) or {}
        now = iso(utcnow())
        with closing(get_db()) as conn:
            row = fetchone(conn, "SELECT * FROM mail_templates WHERE id = ?", (template_id,))
            if not row:
                return jsonify({"error": "Şablon bulunamadı."}), 404
            execute(
                conn,
                """
                UPDATE mail_templates SET name = ?, subject = ?, html_body = ?, text_body = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    (data.get("name") if "name" in data else row["name"]).strip(),
                    (data.get("subject") if "subject" in data else row["subject"] or "").strip(),
                    data.get("html_body") if "html_body" in data else row["html_body"] or "",
                    data.get("text_body") if "text_body" in data else row["text_body"] or "",
                    now,
                    template_id,
                ),
            )
            conn.commit()
            row = fetchone(conn, "SELECT * FROM mail_templates WHERE id = ?", (template_id,))
        return jsonify({"template": _row(row)})

    @bp.route("/templates/<int:template_id>", methods=["DELETE"])
    @mail_perm(*MAIL_TPL)
    def delete_template(template_id):
        with closing(get_db()) as conn:
            execute(conn, "DELETE FROM mail_templates WHERE id = ?", (template_id,))
            conn.commit()
        return jsonify({"ok": True})

    # ── Campaigns ──────────────────────────────────────────────
    @bp.route("/campaigns", methods=["GET"])
    @mail_perm(*MAIL_CAMP)
    def list_campaigns():
        with closing(get_db()) as conn:
            rows = _rows(fetchall(conn, "SELECT * FROM mail_campaigns ORDER BY id DESC"))
            for r in rows:
                r["recipient_count"] = scalar(
                    conn,
                    "SELECT COUNT(*) FROM mail_campaign_recipients WHERE campaign_id = ?",
                    (r["id"],),
                ) or 0
        return jsonify({"campaigns": rows})

    @bp.route("/campaigns", methods=["POST"])
    @mail_perm(*MAIL_CAMP)
    def create_campaign():
        data = request.get_json(silent=True) or {}
        name = (data.get("name") or "").strip()
        if not name:
            return jsonify({"error": "Kampanya adı gerekli."}), 400
        template_id = data.get("template_id")
        domain_id = data.get("domain_id")
        if not template_id:
            return jsonify({"error": "Şablon seçin."}), 400
        if not domain_id:
            return jsonify({"error": "Domain seçin."}), 400
        now = iso(utcnow())
        tag_filter = (data.get("tag_filter") or "").strip()
        with closing(get_db()) as conn:
            if not fetchone(conn, "SELECT id FROM mail_templates WHERE id = ?", (template_id,)):
                return jsonify({"error": "Şablon bulunamadı."}), 404
            if not fetchone(conn, "SELECT id FROM mail_domains WHERE id = ?", (domain_id,)):
                return jsonify({"error": "Domain bulunamadı."}), 404
            cid = insert_returning_id(
                conn,
                """
                INSERT INTO mail_campaigns
                (name, campaign_type, template_id, domain_id, status, tag_filter, notes, created_at, updated_at)
                VALUES (?, 'bulk', ?, ?, 'draft', ?, ?, ?, ?)
                """,
                (name, template_id, domain_id, tag_filter, (data.get("notes") or "").strip(), now, now),
            )
            # Attach recipients: all active contacts, optionally filtered by tag
            contacts = _rows(fetchall(
                conn,
                "SELECT * FROM mail_contacts WHERE unsubscribed = 0 ORDER BY id ASC",
            ))
            attached = 0
            for c in contacts:
                tags = _parse_tags(c.get("tags"))
                if tag_filter and tag_filter not in tags:
                    continue
                try:
                    insert_returning_id(
                        conn,
                        """
                        INSERT INTO mail_campaign_recipients (campaign_id, contact_id, status, created_at)
                        VALUES (?, ?, 'pending', ?)
                        """,
                        (cid, c["id"], now),
                    )
                    attached += 1
                except Exception:
                    pass
            conn.commit()
            row = fetchone(conn, "SELECT * FROM mail_campaigns WHERE id = ?", (cid,))
            out = _row(row)
            out["recipient_count"] = attached
        return jsonify({"campaign": out}), 201

    @bp.route("/campaigns/<int:campaign_id>", methods=["PATCH"])
    @mail_perm(*MAIL_CAMP)
    def update_campaign(campaign_id):
        data = request.get_json(silent=True) or {}
        now = iso(utcnow())
        with closing(get_db()) as conn:
            row = fetchone(conn, "SELECT * FROM mail_campaigns WHERE id = ?", (campaign_id,))
            if not row:
                return jsonify({"error": "Kampanya bulunamadı."}), 404
            if row["status"] not in ("draft",):
                return jsonify({"error": "Sadece taslak kampanyalar düzenlenebilir."}), 400
            execute(
                conn,
                """
                UPDATE mail_campaigns SET name = ?, template_id = ?, domain_id = ?,
                    tag_filter = ?, notes = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    (data.get("name") if "name" in data else row["name"]).strip(),
                    data.get("template_id") if "template_id" in data else row["template_id"],
                    data.get("domain_id") if "domain_id" in data else row["domain_id"],
                    (data.get("tag_filter") if "tag_filter" in data else row["tag_filter"] or "").strip(),
                    (data.get("notes") if "notes" in data else row["notes"] or "").strip(),
                    now,
                    campaign_id,
                ),
            )
            conn.commit()
            row = fetchone(conn, "SELECT * FROM mail_campaigns WHERE id = ?", (campaign_id,))
        return jsonify({"campaign": _row(row)})

    @bp.route("/campaigns/<int:campaign_id>", methods=["DELETE"])
    @mail_perm(*MAIL_CAMP)
    def delete_campaign(campaign_id):
        with closing(get_db()) as conn:
            execute(conn, "DELETE FROM mail_campaign_recipients WHERE campaign_id = ?", (campaign_id,))
            execute(conn, "DELETE FROM mail_campaigns WHERE id = ?", (campaign_id,))
            conn.commit()
        return jsonify({"ok": True})

    @bp.route("/campaigns/<int:campaign_id>/queue", methods=["POST"])
    @mail_perm(*MAIL_CAMP)
    def queue_campaign(campaign_id):
        now = iso(utcnow())
        with closing(get_db()) as conn:
            camp = fetchone(conn, "SELECT * FROM mail_campaigns WHERE id = ?", (campaign_id,))
            if not camp:
                return jsonify({"error": "Kampanya bulunamadı."}), 404
            if camp["status"] not in ("draft", "queued"):
                return jsonify({"error": f"Kampanya durumu uygun değil: {camp['status']}"}), 400
            tpl = fetchone(conn, "SELECT * FROM mail_templates WHERE id = ?", (camp["template_id"],))
            if not tpl:
                return jsonify({"error": "Şablon bulunamadı."}), 400
            recipients = _rows(fetchall(
                conn,
                """
                SELECT r.id AS recipient_id, r.contact_id, c.email, c.phone, c.name, c.tags
                FROM mail_campaign_recipients r
                JOIN mail_contacts c ON c.id = r.contact_id
                WHERE r.campaign_id = ? AND r.status = 'pending' AND c.unsubscribed = 0
                """,
                (campaign_id,),
            ))
            execute(
                conn,
                "UPDATE mail_campaigns SET status = 'sending', queued_at = ?, updated_at = ? WHERE id = ?",
                (now, now, campaign_id),
            )
            sent = 0
            for rec in recipients:
                contact = {
                    "name": rec.get("name") or "",
                    "email": rec.get("email") or "",
                    "phone": rec.get("phone") or "",
                }
                subject = _render_template(tpl["subject"], contact)
                send_id, status = _stub_send(
                    conn,
                    channel="bulk",
                    to_email=rec["email"],
                    subject=subject,
                    contact=contact,
                    campaign_id=campaign_id,
                    contact_id=rec["contact_id"],
                    template_id=camp["template_id"],
                    domain_id=camp["domain_id"],
                    to_phone=rec.get("phone") or "",
                )
                execute(
                    conn,
                    "UPDATE mail_campaign_recipients SET status = ?, send_id = ? WHERE id = ?",
                    (status, send_id, rec["recipient_id"]),
                )
                sent += 1
            execute(
                conn,
                "UPDATE mail_campaigns SET status = 'done', finished_at = ?, updated_at = ? WHERE id = ?",
                (now, now, campaign_id),
            )
            conn.commit()
        return jsonify({
            "ok": True,
            "queued": sent,
            "mode": "stub",
            "message": f"{sent} alıcı için stub gönderim kaydı oluşturuldu. Alibaba bağlanınca gerçek iletim aktif olur.",
        })

    # ── Sends / Reports ────────────────────────────────────────
    @bp.route("/sends", methods=["GET"])
    @mail_perm(*MAIL_REP)
    def list_sends():
        status = (request.args.get("status") or "").strip()
        channel = (request.args.get("channel") or "").strip()
        limit = min(int(request.args.get("limit") or 200), 1000)
        with closing(get_db()) as conn:
            sql = "SELECT * FROM mail_sends WHERE 1=1"
            params = []
            if status:
                sql += " AND status = ?"
                params.append(status)
            if channel:
                sql += " AND channel = ?"
                params.append(channel)
            sql += " ORDER BY id DESC LIMIT ?"
            params.append(limit)
            rows = _rows(fetchall(conn, sql, tuple(params)))
        return jsonify({"sends": rows, "count": len(rows)})

    @bp.route("/reports/summary", methods=["GET"])
    @mail_perm(*MAIL_REP)
    def reports_summary():
        with closing(get_db()) as conn:
            by_status = _rows(fetchall(
                conn,
                "SELECT status, COUNT(*) AS cnt FROM mail_sends GROUP BY status ORDER BY cnt DESC",
            ))
            by_channel = _rows(fetchall(
                conn,
                "SELECT channel, COUNT(*) AS cnt FROM mail_sends GROUP BY channel ORDER BY cnt DESC",
            ))
            recent = _rows(fetchall(
                conn,
                "SELECT * FROM mail_sends ORDER BY id DESC LIMIT 20",
            ))
        return jsonify({
            "by_status": by_status,
            "by_channel": by_channel,
            "recent": recent,
        })

    # ── Domains / Settings ─────────────────────────────────────
    @bp.route("/domains", methods=["GET"])
    @mail_perm(*MAIL_SET)
    def list_domains():
        with closing(get_db()) as conn:
            rows = _rows(fetchall(conn, "SELECT * FROM mail_domains ORDER BY id ASC"))
        return jsonify({"domains": rows})

    @bp.route("/domains/<int:domain_id>", methods=["PATCH"])
    @mail_perm(*MAIL_SET)
    def update_domain(domain_id):
        data = request.get_json(silent=True) or {}
        with closing(get_db()) as conn:
            row = fetchone(conn, "SELECT * FROM mail_domains WHERE id = ?", (domain_id,))
            if not row:
                return jsonify({"error": "Domain bulunamadı."}), 404
            execute(
                conn,
                """
                UPDATE mail_domains SET
                    from_name = ?, from_local = ?, status = ?, dns_status = ?, notes = ?
                WHERE id = ?
                """,
                (
                    (data.get("from_name") if "from_name" in data else row["from_name"] or "").strip(),
                    (data.get("from_local") if "from_local" in data else row["from_local"] or "noreply").strip(),
                    (data.get("status") if "status" in data else row["status"] or "pending").strip(),
                    (data.get("dns_status") if "dns_status" in data else row["dns_status"] or "unconfigured").strip(),
                    (data.get("notes") if "notes" in data else row["notes"] or "").strip(),
                    domain_id,
                ),
            )
            conn.commit()
            row = fetchone(conn, "SELECT * FROM mail_domains WHERE id = ?", (domain_id,))
        return jsonify({"domain": _row(row)})

    @bp.route("/settings", methods=["GET"])
    @mail_perm(*MAIL_SET)
    def get_settings():
        keys = (
            "provider_mode", "smtp_host", "smtp_port", "smtp_user", "smtp_password",
            "webhook_secret", "default_domain_id",
        )
        with closing(get_db()) as conn:
            settings = {k: get_mail_setting(conn, k, "") or "" for k in keys}
            # Mask password
            pw = settings.get("smtp_password") or ""
            settings["smtp_password_set"] = bool(pw)
            settings["smtp_password"] = ""
            settings["webhook_secret_masked"] = _mask_secret(settings.get("webhook_secret") or "")
            domains = _rows(fetchall(conn, "SELECT * FROM mail_domains ORDER BY id ASC"))
        return jsonify({"settings": settings, "domains": domains})

    @bp.route("/settings", methods=["PATCH"])
    @mail_perm(*MAIL_SET)
    def patch_settings():
        data = request.get_json(silent=True) or {}
        allowed = {
            "provider_mode", "smtp_host", "smtp_port", "smtp_user", "smtp_password",
            "webhook_secret", "default_domain_id",
        }
        with closing(get_db()) as conn:
            if data.get("rotate_webhook_secret"):
                upsert_mail_setting(conn, "webhook_secret", secrets.token_hex(24))
            for key, val in data.items():
                if key not in allowed:
                    continue
                if key == "smtp_password" and (val is None or val == ""):
                    continue  # empty = keep existing
                upsert_mail_setting(conn, key, "" if val is None else str(val).strip())
            conn.commit()
            settings = {k: get_mail_setting(conn, k, "") or "" for k in allowed}
            pw = settings.get("smtp_password") or ""
            settings["smtp_password_set"] = bool(pw)
            settings["smtp_password"] = ""
            settings["webhook_secret_masked"] = _mask_secret(settings.get("webhook_secret") or "")
        return jsonify({"settings": settings})

    def _mask_secret(s):
        if not s:
            return ""
        if len(s) <= 8:
            return "•" * len(s)
        return s[:4] + "•" * (len(s) - 8) + s[-4:]

    # ── IVR ────────────────────────────────────────────────────
    @bp.route("/ivr/rules", methods=["GET"])
    @mail_perm(*MAIL_IVR)
    def get_ivr_rules():
        with closing(get_db()) as conn:
            rows = _rows(fetchall(conn, "SELECT * FROM mail_ivr_rules ORDER BY id ASC"))
        return jsonify({"rules": rows})

    @bp.route("/ivr/rules/<int:rule_id>", methods=["PATCH"])
    @mail_perm(*MAIL_IVR)
    def patch_ivr_rule(rule_id):
        data = request.get_json(silent=True) or {}
        with closing(get_db()) as conn:
            row = fetchone(conn, "SELECT * FROM mail_ivr_rules WHERE id = ?", (rule_id,))
            if not row:
                return jsonify({"error": "Kural bulunamadı."}), 404
            execute(
                conn,
                """
                UPDATE mail_ivr_rules SET name = ?, active = ?, template_id = ?,
                    domain_id = ?, delay_seconds = ?
                WHERE id = ?
                """,
                (
                    (data.get("name") if "name" in data else row["name"] or "").strip(),
                    1 if data.get("active", row["active"]) else 0,
                    data.get("template_id") if "template_id" in data else row["template_id"],
                    data.get("domain_id") if "domain_id" in data else row["domain_id"],
                    int(data.get("delay_seconds") if "delay_seconds" in data else row["delay_seconds"] or 0),
                    rule_id,
                ),
            )
            conn.commit()
            row = fetchone(conn, "SELECT * FROM mail_ivr_rules WHERE id = ?", (rule_id,))
        return jsonify({"rule": _row(row)})

    @bp.route("/ivr/events", methods=["GET"])
    @mail_perm(*MAIL_IVR)
    def list_ivr_events():
        limit = min(int(request.args.get("limit") or 100), 500)
        with closing(get_db()) as conn:
            rows = _rows(fetchall(
                conn,
                "SELECT * FROM mail_ivr_events ORDER BY id DESC LIMIT ?",
                (limit,),
            ))
        return jsonify({"events": rows})

    @bp.route("/webhooks/ivr", methods=["POST"])
    def ivr_webhook():
        """Harici IVR santralinden çağrı cevabı bildirimi.
        Auth: X-Mailing-Webhook-Secret header veya ?secret= query.
        Body JSON: { phone, email?, answered_at?, name? }
        """
        data = request.get_json(silent=True) or {}
        secret = (
            request.headers.get("X-Mailing-Webhook-Secret")
            or request.args.get("secret")
            or ""
        ).strip()
        now = iso(utcnow())
        with closing(get_db()) as conn:
            expected = (get_mail_setting(conn, "webhook_secret", "") or "").strip()
            if not expected or secret != expected:
                return jsonify({"error": "Unauthorized"}), 401

            phone = (data.get("phone") or data.get("tel") or "").strip()
            email = (data.get("email") or "").strip().lower()
            answered_at = (data.get("answered_at") or now).strip()
            name = (data.get("name") or "").strip()

            event_id = insert_returning_id(
                conn,
                """
                INSERT INTO mail_ivr_events
                (phone, email, answered_at, contact_id, send_id, status, payload, error, created_at)
                VALUES (?, ?, ?, NULL, NULL, 'received', ?, '', ?)
                """,
                (phone, email, answered_at, json.dumps(data, ensure_ascii=False), now),
            )

            rule = fetchone(
                conn,
                "SELECT * FROM mail_ivr_rules WHERE active = 1 ORDER BY id ASC LIMIT 1",
            )
            if not rule:
                execute(
                    conn,
                    "UPDATE mail_ivr_events SET status = ?, error = ? WHERE id = ?",
                    ("skipped", "Aktif IVR kuralı yok", event_id),
                )
                conn.commit()
                return jsonify({"ok": True, "event_id": event_id, "status": "skipped", "reason": "no_active_rule"})

            if not rule["template_id"] or not rule["domain_id"]:
                execute(
                    conn,
                    "UPDATE mail_ivr_events SET status = ?, error = ? WHERE id = ?",
                    ("skipped", "IVR kuralında şablon/domain eksik", event_id),
                )
                conn.commit()
                return jsonify({"ok": True, "event_id": event_id, "status": "skipped", "reason": "rule_incomplete"})

            # Match contact by phone or email
            contact = None
            if phone:
                contact = fetchone(
                    conn,
                    "SELECT * FROM mail_contacts WHERE phone != '' AND phone = ? LIMIT 1",
                    (phone,),
                )
            if not contact and email:
                contact = fetchone(
                    conn,
                    "SELECT * FROM mail_contacts WHERE LOWER(email) = ? LIMIT 1",
                    (email,),
                )
            # Auto-create contact if email provided
            if not contact and email and EMAIL_RE.match(email):
                cid = insert_returning_id(
                    conn,
                    """
                    INSERT INTO mail_contacts
                    (email, phone, name, tags, source, unsubscribed, notes, created_at, updated_at)
                    VALUES (?, ?, ?, ?, 'ivr', 0, '', ?, ?)
                    """,
                    (email, phone, name, _tags_json(["ivr"]), now, now),
                )
                contact = fetchone(conn, "SELECT * FROM mail_contacts WHERE id = ?", (cid,))

            contact = _row(contact) if contact else None

            if not contact or not contact.get("email"):
                execute(
                    conn,
                    "UPDATE mail_ivr_events SET status = ?, error = ? WHERE id = ?",
                    ("no_contact", "Eşleşen kontak/e-posta yok", event_id),
                )
                conn.commit()
                return jsonify({"ok": True, "event_id": event_id, "status": "no_contact"})

            if contact.get("unsubscribed"):
                execute(
                    conn,
                    "UPDATE mail_ivr_events SET status = ?, contact_id = ?, error = ? WHERE id = ?",
                    ("unsubscribed", contact["id"], "Kontak abonelikten çıkmış", event_id),
                )
                conn.commit()
                return jsonify({"ok": True, "event_id": event_id, "status": "unsubscribed"})

            tpl = fetchone(conn, "SELECT * FROM mail_templates WHERE id = ?", (rule["template_id"],))
            if not tpl:
                execute(
                    conn,
                    "UPDATE mail_ivr_events SET status = ?, contact_id = ?, error = ? WHERE id = ?",
                    ("error", contact["id"], "Şablon bulunamadı", event_id),
                )
                conn.commit()
                return jsonify({"ok": False, "event_id": event_id, "status": "error"}), 400

            contact_d = _contact_out(contact)
            subject = _render_template(tpl["subject"], contact_d)
            send_id, status = _stub_send(
                conn,
                channel="ivr",
                to_email=contact_d["email"],
                subject=subject,
                contact=contact_d,
                contact_id=contact_d["id"],
                template_id=rule["template_id"],
                domain_id=rule["domain_id"],
                to_phone=phone or contact_d.get("phone") or "",
            )
            execute(
                conn,
                "UPDATE mail_ivr_events SET status = ?, contact_id = ?, send_id = ? WHERE id = ?",
                (status, contact_d["id"], send_id, event_id),
            )
            conn.commit()
        return jsonify({
            "ok": True,
            "event_id": event_id,
            "send_id": send_id,
            "status": status,
            "mode": "stub",
        })

    return bp
