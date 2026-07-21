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


def _smtp_login_once(host, port, user, password) -> None:
    port = int(port or 465)
    context = ssl.create_default_context()
    if port == 465:
        with smtplib.SMTP_SSL(host, port, timeout=20, context=context) as smtp:
            smtp.login(user, password or "")
    else:
        with smtplib.SMTP(host, port, timeout=20) as smtp:
            smtp.ehlo()
            try:
                smtp.starttls(context=context)
                smtp.ehlo()
            except smtplib.SMTPException:
                pass
            smtp.login(user, password or "")


# DirectMail bölge hostları (yanlış host → bazen 535)
_ALI_SMTP_HOSTS = (
    "smtpdm.aliyun.com",
    "smtpdm-ap-southeast-1.aliyuncs.com",
    "smtpdm-eu-central-1.aliyuncs.com",
    "smtpdm-us-east-1.aliyuncs.com",
    "smtpdm-ap-southeast-1.aliyun.com",
)


def smtp_login_test(conn, *, domain_id=None, override_password=None, override_user=None,
                    override_host=None, override_port=None, probe_hosts=True) -> dict:
    """Ayarlar SMTP login. Birden fazla user/host dener — 535 teşhisi için."""
    cfg_host = (override_host or get_mail_setting(conn, "smtp_host", "") or "").strip()
    port = int((override_port or get_mail_setting(conn, "smtp_port", "465") or "465").strip() or 465)
    settings_user = (override_user or get_mail_setting(conn, "smtp_user", "") or "").strip()
    password = (override_password if override_password is not None
                else (get_mail_setting(conn, "smtp_password", "") or "")).strip()
    from_email, _from_name = _domain_from(conn, domain_id)
    domain_name = from_email.split("@")[-1] if "@" in (from_email or "") else ""

    users = []
    for u in (settings_user, from_email,
              f"info@{domain_name}" if domain_name else "",
              f"noreply@{domain_name}" if domain_name else ""):
        u = (u or "").strip().lower()
        if u and "@" in u and u not in users:
            users.append(u)

    if not password and domain_id:
        drow = fetchone(conn, "SELECT smtp_password, smtp_password_enc FROM mail_domains WHERE id = ?", (domain_id,))
        password = _resolve_domain_smtp_password(drow)

    if not password:
        return {
            "ok": False,
            "error": "SMTP şifre boş — Ayarlar’a DirectMail SMTP şifresini kaydet",
            "users_tried": users,
            "password_len": 0,
        }

    hosts = []
    for h in ((cfg_host,) + (_ALI_SMTP_HOSTS if probe_hosts else ())):
        h = (h or "").strip()
        if h and h not in hosts:
            hosts.append(h)
    if not hosts:
        return {"ok": False, "error": "SMTP host boş", "password_len": len(password)}

    attempts = []
    for host in hosts:
        for user in users:
            try:
                _smtp_login_once(host, port, user, password)
                return {
                    "ok": True,
                    "message": f"SMTP login OK · user={user} @ {host}:{port}",
                    "user": user,
                    "host": host,
                    "port": port,
                    "from_email": from_email,
                    "password_len": len(password),
                    "hint": (
                        f"Çalışan kombinasyon: User={user}, Host={host}. "
                        "Ayarlar’a bunları kaydet; Platform from_local bu user ile aynı olsun."
                    ),
                }
            except Exception as exc:
                attempts.append({
                    "user": user,
                    "host": host,
                    "error": str(exc).strip()[:180],
                })

    return {
        "ok": False,
        "error": "Tüm user/host kombinasyonları 535/fail — şifre veya bölge yanlış",
        "password_len": len(password),
        "from_email": from_email,
        "settings_user": settings_user,
        "attempts": attempts[:12],
        "hint": (
            "1) Alibaba Sender Addresses’te şifreyi hangi adrese set ettin? "
            "Panel User aynısı olmalı (info@ vs noreply@). "
            "2) DirectMail bölgesi SG ise host: smtpdm-ap-southeast-1.aliyuncs.com "
            "3) Şifre setinden sonra ~10 dk bekle."
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

    # Alibaba kuralı: AUTH user == MAIL FROM. Ayarlar user+şifre varsa ikisini de ona kilitle.
    if settings_password and settings_user and "@" in settings_user:
        user = settings_user.strip().lower()
        password = settings_password
        from_email = user  # From'u auth ile eşitle — aksi halde 535/436
        auth_source = "settings"
    elif domain_smtp_pw:
        user = from_email
        password = domain_smtp_pw
        auth_source = "domain"
    elif settings_password:
        user = from_email
        password = settings_password
        auth_source = "settings-from"
    else:
        user = settings_user or from_email
        password = ""
        auth_source = "none"

    if not password:
        err = (
            "SMTP şifresi boş. Ayarlar → SMTP Password’e DirectMail SMTP şifresini kaydet. "
            "SMTP User = Alibaba’da şifre set ettiğin adres (örn. info@… veya noreply@…)."
        )
        execute(conn, "UPDATE mail_sends SET status = 'failed', error = ? WHERE id = ?", (err, send_id))
        return send_id, "failed", err

    extra = list_unsubscribe_headers(unsub_http) if unsub_http else None

    # Yanlış bölge host’u 535 verebiliyor — sırayla dene
    host_list = []
    for h in (host,) + _ALI_SMTP_HOSTS:
        h = (h or "").strip()
        if h and h not in host_list:
            host_list.append(h)

    last_err = ""
    for try_host in host_list:
        try:
            msg_id = _smtp_send(
                host=try_host,
                port=port,
                user=user,
                password=password,
                from_email=from_email,
                from_name=from_name,
                to_email=to_email,
                subject=subject,
                html_body=tracked_html,
                text_body=tracked_text,
                extra_headers=extra,
            )
            if try_host != host:
                try:
                    from database import upsert_mail_setting
                    upsert_mail_setting(conn, "smtp_host", try_host)
                except Exception:
                    pass
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
            last_err = str(exc).strip()[:400] or "SMTP gönderim hatası"
            if "535" not in last_err and "Authentication" not in last_err and "auth" not in last_err.lower():
                # Timeout / network — diğer host’a geç; auth değilse de dene
                continue
            continue

    err = f"{last_err} [auth={auth_source}; user={user}; hosts_tried={len(host_list)}]"
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
