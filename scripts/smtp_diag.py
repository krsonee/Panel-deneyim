#!/usr/bin/env python3
"""Mikromail DB'deki SMTP ayarını oku + login dene (şifreyi yazdırmaz).

Render mikromail Shell:

  python scripts/smtp_diag.py

İsteğe bağlı yeni şifre ile dene (DB'ye yazmaz):

  SMTP_TRY_PASSWORD='yenisifre' python scripts/smtp_diag.py
"""
from __future__ import annotations

import os
import smtplib
import ssl
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))


HOSTS = (
    "smtpdm-ap-southeast-1.aliyuncs.com",
    "smtpdm-ap-southeast-1.aliyun.com",
    "smtpdm.aliyun.com",
    "smtpdm-eu-central-1.aliyuncs.com",
    "smtpdm-us-east-1.aliyuncs.com",
)


def main():
    os.environ.setdefault("SERVICE_MODE", "mailing")
    from contextlib import closing
    from database import get_db, get_mail_setting

    with closing(get_db()) as conn:
        host = (get_mail_setting(conn, "smtp_host", "") or "").strip()
        port = int((get_mail_setting(conn, "smtp_port", "465") or "465").strip() or 465)
        user = (get_mail_setting(conn, "smtp_user", "") or "").strip().lower()
        password = (os.environ.get("SMTP_TRY_PASSWORD") or get_mail_setting(conn, "smtp_password", "") or "")
        password = (
            str(password)
            .replace("\u200b", "")
            .replace("\ufeff", "")
            .replace("\r", "")
            .replace("\n", "")
            .strip()
        )
        mode = get_mail_setting(conn, "provider_mode", "")
        domains = []
        try:
            from database import fetchall

            for r in fetchall(conn, "SELECT id, domain, from_local FROM mail_domains ORDER BY id") or []:
                domains.append(f"{r['id']}:{r['from_local']}@{r['domain']}")
        except Exception as exc:
            domains = [f"err:{exc}"]

    print("=== Mikromail SMTP diag ===")
    print(f"mode={mode!r}")
    print(f"host_in_db={host!r}")
    print(f"port={port}")
    print(f"user={user!r}")
    print(f"password_len={len(password)} password_source={'env' if os.environ.get('SMTP_TRY_PASSWORD') else 'db'}")
    print(f"domains={domains}")
    if not password:
        print("FAIL: şifre boş — Ayarlar'da SMTP Password yazıp kaydet")
        sys.exit(2)
    if not user or "@" not in user:
        print("FAIL: smtp_user geçersiz")
        sys.exit(2)

    users = [user]
    if user.startswith("info@"):
        users.append(user.replace("info@", "noreply@", 1))
    elif user.startswith("noreply@"):
        users.append(user.replace("noreply@", "info@", 1))

    host_list = []
    for h in (host,) + HOSTS:
        h = (h or "").strip()
        if h and h not in host_list:
            host_list.append(h)

    from mail_delivery import is_account_unavailable_error, smtp_error_brief

    def _probe(s, u):
        s.login(u, password)
        # MAIL FROM + RSET: DATA yok, mail gönderilmez; 551 login'de mi zarfta mı görünür.
        code, resp = s.mail(u)
        s.rset()
        if code >= 400:
            raise smtplib.SMTPSenderRefused(code, resp, u)

    ctx = ssl.create_default_context()
    ok = False
    account_blocked = False
    for h in host_list:
        for u in users:
            try:
                if port == 465:
                    with smtplib.SMTP_SSL(h, port, timeout=25, context=ctx) as s:
                        _probe(s, u)
                else:
                    with smtplib.SMTP(h, port, timeout=25) as s:
                        s.ehlo()
                        try:
                            s.starttls(context=ctx)
                            s.ehlo()
                        except smtplib.SMTPException:
                            pass
                        _probe(s, u)
                print(f"OK login+MAIL FROM user={u} host={h}:{port}")
                ok = True
                break
            except Exception as exc:
                print(f"FAIL user={u} host={h} -> {smtp_error_brief(exc)}")
                if is_account_unavailable_error(exc):
                    account_blocked = True
        if ok:
            break

    if account_blocked and not ok:
        print("---")
        print("Sonuç: 551 Main account unavailable — sender tanınıyor ama 551 veren bölgede gönderime kapalı.")
        print("ud010301 = o bölgede sender yok, ud010201 = sender var/şifre yanlış.")
        print("1) 551 veren host'un bölgesinde DirectMail → Sender Addresses → adres durumu + Set SMTP Password")
        print("2) Email Domains → domain 'Verified' mi; Overview → Account Status")
        try:
            from mail_alibaba_report import account_status

            with closing(get_db()) as conn:
                st = account_status(conn)
            if st.get("ok"):
                print(
                    f"API ({st['region']}): UserStatus={st['user_status']} [{st['user_status_label']}] "
                    f"seviye={st.get('quota_level')} günlük={st.get('daily_quota')} kanal={st.get('ip_channel_type')}"
                )
            else:
                print(f"API DescAccountSummary okunamadı: {st.get('error')}")
        except Exception as exc:
            print(f"API DescAccountSummary hata: {exc}")
        sys.exit(3)

    if not ok:
        print("---")
        print("Sonuç: Alibaba login kabul etmiyor.")
        print("1) dm.console.alibabacloud.com → Sender Addresses → info@ satırı VAR mı?")
        print("2) Set SMTP Password → yeni şifre → 10 dk bekle")
        print("3) Bölge SG ise host tam: smtpdm-ap-southeast-1.aliyuncs.com")
        print("4) Shell'de dene: SMTP_TRY_PASSWORD='yenisifre' python scripts/smtp_diag.py")
        sys.exit(1)
    sys.exit(0)


if __name__ == "__main__":
    main()
