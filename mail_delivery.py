"""Mail gönderim katmanı — stub simülasyon veya gerçek SMTP (Alibaba DirectMail)."""

from __future__ import annotations

import smtplib
import ssl
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from database import (
    fetchone,
    get_mail_setting,
    insert_returning_id,
    iso,
    utcnow,
)


def _domain_from(conn, domain_id):
    if not domain_id:
        return "noreply@localhost", "MakroPanel"
    row = fetchone(conn, "SELECT * FROM mail_domains WHERE id = ?", (domain_id,))
    if not row:
        return "noreply@localhost", "MakroPanel"
    row = dict(row)
    local = (row.get("from_local") or "noreply").strip() or "noreply"
    domain = (row.get("domain") or "localhost").strip() or "localhost"
    name = (row.get("from_name") or domain).strip() or domain
    return f"{local}@{domain}", name


def _smtp_send(*, host, port, user, password, from_email, from_name, to_email, subject, html_body, text_body):
    msg = EmailMessage()
    msg["Subject"] = subject or "(konu yok)"
    msg["From"] = formataddr((from_name, from_email))
    msg["To"] = to_email
    msg["Message-ID"] = make_msgid(domain=from_email.split("@")[-1] if "@" in from_email else "localhost")
    text = (text_body or "").strip()
    html = (html_body or "").strip()
    if text:
        msg.set_content(text)
    else:
        msg.set_content("Bu e-postayı HTML destekleyen bir istemcide görüntüleyin.")
    if html:
        msg.add_alternative(html, subtype="html")

    port = int(port or 465)
    context = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=30, context=context) as smtp:
            if user:
                smtp.login(user, password or "")
            smtp.send_message(msg)
    else:
        with smtplib.SMTP(host, port, timeout=30) as smtp:
            smtp.ehlo()
            try:
                smtp.starttls(context=context)
                smtp.ehlo()
            except smtplib.SMTPException:
                pass
            if user:
                smtp.login(user, password or "")
            smtp.send_message(msg)
    return (msg["Message-ID"] or "").strip("<>")


def deliver_mail(
    conn,
    *,
    channel,
    to_email,
    subject,
    contact=None,
    campaign_id=None,
    contact_id=None,
    template_id=None,
    domain_id=None,
    to_phone="",
    html_body="",
    text_body="",
    inject_tracking=None,
):
    """Tek mail gönder / simüle et.

    inject_tracking: optional callable(conn, body, send_id=..., contact_id=..., campaign_id=..., as_html=...) -> body
    Dönüş: (send_id, status, error_message)
    """
    now = iso(utcnow())
    mode = (get_mail_setting(conn, "provider_mode", "stub") or "stub").strip().lower()
    to_email = (to_email or "").strip().lower()
    if not to_email:
        return None, "failed", "Alıcı e-posta yok"

    # Önce kayıt aç (tracking send_id ister)
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
            "queued",
            "",
            "",
            None,
            None,
            None,
            now,
        ),
    )

    tracked_html = html_body or ""
    tracked_text = text_body or ""
    if inject_tracking:
        if tracked_html:
            tracked_html = inject_tracking(
                conn, tracked_html, send_id=send_id, contact_id=contact_id,
                campaign_id=campaign_id, as_html=True,
            ) or tracked_html
        elif tracked_text:
            tracked_text = inject_tracking(
                conn, tracked_text, send_id=send_id, contact_id=contact_id,
                campaign_id=campaign_id, as_html=False,
            ) or tracked_text

    if mode != "smtp":
        msg_id = f"stub-{send_id}-{now[-8:]}"
        from database import execute
        execute(
            conn,
            """
            UPDATE mail_sends
            SET status = 'simulated', provider_msg_id = ?, sent_at = ?, error = ''
            WHERE id = ?
            """,
            (msg_id, now, send_id),
        )
        return send_id, "simulated", ""

    host = (get_mail_setting(conn, "smtp_host", "") or "").strip()
    port = (get_mail_setting(conn, "smtp_port", "465") or "465").strip()
    user = (get_mail_setting(conn, "smtp_user", "") or "").strip()
    password = get_mail_setting(conn, "smtp_password", "") or ""
    if not host:
        from database import execute
        execute(
            conn,
            """
            UPDATE mail_sends
            SET status = 'failed', error = ?
            WHERE id = ?
            """,
            ("SMTP host tanımlı değil (Ayarlar → Gönderim sağlayıcı).", send_id),
        )
        return send_id, "failed", "SMTP host tanımlı değil"

    from_email, from_name = _domain_from(conn, domain_id)
    # DirectMail: SMTP login = From adresi olmalı. Domain'e özel şifre varsa onu kullan.
    domain_smtp_pw = ""
    if domain_id:
        drow = fetchone(conn, "SELECT smtp_password FROM mail_domains WHERE id = ?", (domain_id,))
        if drow:
            domain_smtp_pw = (dict(drow).get("smtp_password") or "").strip()
    if domain_smtp_pw:
        user = from_email
        password = domain_smtp_pw
    else:
        user_domain = user.split("@")[-1].lower() if "@" in (user or "") else ""
        from_domain = from_email.split("@")[-1].lower() if "@" in (from_email or "") else ""
        if user_domain and from_domain and user_domain != from_domain:
            err = (
                f"SMTP kullanıcı ({user}) ile gönderen domain ({from_email}) uyuşmuyor. "
                "Ayarlar → Domain düzenle → bu domain için DirectMail SMTP şifresini kaydet."
            )
            from database import execute
            execute(
                conn,
                """
                UPDATE mail_sends
                SET status = 'failed', error = ?
                WHERE id = ?
                """,
                (err, send_id),
            )
            return send_id, "failed", err
    try:
        msg_id = _smtp_send(
            host=host,
            port=port,
            user=user,
            password=password,
            from_email=from_email,
            from_name=from_name,
            to_email=to_email,
            subject=subject,
            html_body=tracked_html,
            text_body=tracked_text,
        )
        from database import execute
        execute(
            conn,
            """
            UPDATE mail_sends
            SET status = 'sent', provider_msg_id = ?, sent_at = ?, error = ''
            WHERE id = ?
            """,
            (msg_id or "", now, send_id),
        )
        return send_id, "sent", ""
    except Exception as exc:
        err = str(exc).strip()[:500] or "SMTP gönderim hatası"
        from database import execute
        execute(
            conn,
            """
            UPDATE mail_sends
            SET status = 'failed', error = ?
            WHERE id = ?
            """,
            (err, send_id),
        )
        return send_id, "failed", err
