"""Mail gönderim katmanı — stub simülasyon veya gerçek SMTP (Alibaba DirectMail)."""
from __future__ import annotations

import ssl
import smtplib
from email.message import EmailMessage
from email.utils import formataddr, make_msgid

from database import execute, fetchone, get_mail_setting, insert_returning_id, iso, utcnow


def _domain_from(conn, domain_id):
    if not domain_id:
        return "noreply@localhost", "Mail"
    row = fetchone(conn, "SELECT * FROM mail_domains WHERE id = ?", (domain_id,))
    if not row:
        return "noreply@localhost", "Mail"
    row = dict(row)
    local = (row.get("from_local") or "noreply").strip() or "noreply"
    domain = (row.get("domain") or "localhost").strip()
    name = (row.get("from_name") or domain or "Mail").strip() or "Mail"
    return f"{local}@{domain}", name


def _resolve_domain_smtp_password(row) -> str:
    """Makro panel uyumu: düz smtp_password öncelikli, sonra enc decrypt."""
    if not row:
        return ""
    d = dict(row)
    plain = (d.get("smtp_password") or "").strip()
    enc = (d.get("smtp_password_enc") or "").strip()
    if plain and not plain.startswith("enc:v1:"):
        return plain
    blob = enc or plain
    if not blob:
        return ""
    if blob.startswith("enc:v1:"):
        try:
            from mail_tenant import decrypt_secret

            return (decrypt_secret(blob) or "").strip()
        except Exception:
            return ""
    return blob


def _smtp_send(
    *,
    host,
    port,
    user,
    password,
    from_email,
    from_name,
    to_email,
    subject,
    html_body,
    text_body,
    extra_headers=None,
):
    msg = EmailMessage()
    msg["Subject"] = subject or "(konu yok)"
    msg["From"] = formataddr((from_name, from_email))
    msg["To"] = to_email
    msg["Message-ID"] = make_msgid(domain=from_email.split("@")[-1] if "@" in from_email else "localhost")
    for hk, hv in (extra_headers or {}).items():
        if hv:
            msg[hk] = hv
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


def smtp_login_test(conn, *, domain_id=None) -> dict:
    """Ayarlar SMTP ile login dene (domain eski şifresi ezmesin)."""
    host = (get_mail_setting(conn, "smtp_host", "") or "").strip()
    port = int((get_mail_setting(conn, "smtp_port", "465") or "465").strip() or 465)
    settings_user = (get_mail_setting(conn, "smtp_user", "") or "").strip()
    password = (get_mail_setting(conn, "smtp_password", "") or "").strip()
    from_email, from_name = _domain_from(conn, domain_id)
    # Alibaba: login user = gönderen adres. Ayarlar şifresi öncelik.
    user = from_email if from_email and "@" in from_email else settings_user
    auth_source = "settings"
    if not password and domain_id:
        drow = fetchone(conn, "SELECT smtp_password, smtp_password_enc FROM mail_domains WHERE id = ?", (domain_id,))
        dom_pw = _resolve_domain_smtp_password(drow)
        if dom_pw:
            password = dom_pw
            user = from_email
            auth_source = "domain"
    if not host:
        return {"ok": False, "error": "SMTP host boş", "auth_source": auth_source}
    if not user:
        return {"ok": False, "error": "SMTP user boş", "auth_source": auth_source}
    if not password:
        return {
            "ok": False,
            "error": "SMTP şifre boş — Ayarlar ve/veya Platform domain’e DirectMail SMTP şifresini kaydet",
            "auth_source": auth_source,
            "user": user,
        }
    try:
        context = ssl.create_default_context()
        if port == 465:
            with smtplib.SMTP_SSL(host, port, timeout=20, context=context) as smtp:
                smtp.login(user, password)
        else:
            with smtplib.SMTP(host, port, timeout=20) as smtp:
                smtp.ehlo()
                try:
                    smtp.starttls(context=context)
                    smtp.ehlo()
                except smtplib.SMTPException:
                    pass
                smtp.login(user, password)
        return {
            "ok": True,
            "message": f"SMTP login OK · {user} @ {host}:{port} ({auth_source})",
            "user": user,
            "host": host,
            "port": port,
            "auth_source": auth_source,
            "from_email": from_email,
        }
    except Exception as exc:
        return {
            "ok": False,
            "error": str(exc).strip()[:500],
            "user": user,
            "host": host,
            "port": port,
            "auth_source": auth_source,
            "from_email": from_email,
            "hint": (
                "535 ise Alibaba’da bu adresin SMTP şifresi yanlış. "
                "Hesap şifresi değil — DirectMail → Sender Address → SMTP password. "
                "Render web+worker MAILING_SECRET_KEY aynı olmalı."
            ),
        }


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
    """Tek mail gönder / simüle et. Dönüş: (send_id, status, error_message)"""
    from mail_ops import inject_ops_footer, is_suppressed, list_unsubscribe_headers

    now = iso(utcnow())
    mode = (get_mail_setting(conn, "provider_mode", "stub") or "stub").strip().lower()
    to_email = (to_email or "").strip().lower()
    if not to_email:
        return None, "failed", "Alıcı e-posta yok"

    if is_suppressed(conn, to_email):
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
                channel, campaign_id, contact_id, template_id, domain_id,
                to_email, to_phone or "", subject or "", "skipped", "",
                "Suppression / unsubscribed", None, None, None, now,
            ),
        )
        return send_id, "skipped", "Suppression / unsubscribed"

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
        if tracked_text:
            tracked_text = inject_tracking(
                conn, tracked_text, send_id=send_id, contact_id=contact_id,
                campaign_id=campaign_id, as_html=False,
            ) or tracked_text

    unsub_http = ""
    try:
        if tracked_html:
            tracked_html, unsub_http = inject_ops_footer(
                conn, tracked_html, send_id=send_id, contact_id=contact_id,
                email=to_email, as_html=True,
            )
        elif tracked_text:
            tracked_text, unsub_http = inject_ops_footer(
                conn, tracked_text, send_id=send_id, contact_id=contact_id,
                email=to_email, as_html=False,
            )
        else:
            tracked_html, unsub_http = inject_ops_footer(
                conn, "<p></p>", send_id=send_id, contact_id=contact_id,
                email=to_email, as_html=True,
            )
    except Exception as exc:
        print(f"⚠️  mail ops footer: {exc}")

    if mode != "smtp":
        msg_id = f"stub-{send_id}-{now[-8:]}"
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
    settings_user = (get_mail_setting(conn, "smtp_user", "") or "").strip()
    settings_password = (get_mail_setting(conn, "smtp_password", "") or "").strip()
    if not host:
        execute(
            conn,
            "UPDATE mail_sends SET status = 'failed', error = ? WHERE id = ?",
            ("SMTP host tanımlı değil (Ayarlar → Gönderim sağlayıcı).", send_id),
        )
        return send_id, "failed", "SMTP host tanımlı değil"

    from_email, from_name = _domain_from(conn, domain_id)
    domain_smtp_pw = ""
    if domain_id:
        try:
            drow = fetchone(
                conn,
                "SELECT smtp_password, smtp_password_enc FROM mail_domains WHERE id = ?",
                (domain_id,),
            )
        except Exception:
            drow = fetchone(conn, "SELECT smtp_password FROM mail_domains WHERE id = ?", (domain_id,))
        domain_smtp_pw = _resolve_domain_smtp_password(drow)

    # ÖNEMLİ: Ayarlar şifresi öncelikli.
    # Domain'de eski/yanlış şifre kalırsa 535 yiyorduk; yeni Ayarlar şifresi eziliyordu.
    if settings_password:
        user = from_email  # Alibaba: AUTH user = From adresi
        password = settings_password
        auth_source = "settings"
    elif domain_smtp_pw:
        user = from_email
        password = domain_smtp_pw
        auth_source = "domain"
    else:
        user = settings_user or from_email
        password = ""
        auth_source = "none"

    if not password:
        err = (
            "SMTP şifresi boş. Ayarlar → SMTP Password’e DirectMail’de az önce set ettiğin "
            "şifreyi yapıştırıp kaydet (domain eski şifresi artık öncelikli değil)."
        )
        execute(conn, "UPDATE mail_sends SET status = 'failed', error = ? WHERE id = ?", (err, send_id))
        return send_id, "failed", err

    extra = list_unsubscribe_headers(unsub_http) if unsub_http else None

    def _try_send(smtp_user, smtp_password):
        return _smtp_send(
            host=host,
            port=port,
            user=smtp_user,
            password=smtp_password,
            from_email=from_email,
            from_name=from_name,
            to_email=to_email,
            subject=subject,
            html_body=tracked_html,
            text_body=tracked_text,
            extra_headers=extra,
        )

    try:
        msg_id = _try_send(user, password)
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
        is_auth = "535" in err or "Authentication" in err or "auth" in err.lower()
        if (
            is_auth
            and auth_source == "settings"
            and domain_smtp_pw
            and domain_smtp_pw != password
        ):
            try:
                msg_id = _try_send(from_email, domain_smtp_pw)
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
            except Exception as exc2:
                err = f"535 auth (ayarlar+domain denendi): {str(exc2).strip()[:400]}"
        else:
            err = f"{err} [auth={auth_source}; user={user}]"
        execute(
            conn,
            """
            UPDATE mail_sends
            SET status = 'failed', error = ?, provider_msg_id = ''
            WHERE id = ?
            """,
            (err, send_id),
        )
        return send_id, "failed", err
