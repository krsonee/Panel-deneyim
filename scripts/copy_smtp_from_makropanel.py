#!/usr/bin/env python3
"""Makro panel DB'deki çalışan SMTP ayarını Mikromail DB'ye kopyala.

Render Shell (mikromail) içinde:

  SOURCE_DATABASE_URL='postgres://...makropanel-db...' \\
  python scripts/copy_smtp_from_makropanel.py

SOURCE = makropanel-db connection string (Render → makropanel-db → Connect)
Hedef = mevcut DATABASE_URL (mikromail-db)
"""
from __future__ import annotations

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

KEYS = (
    "provider_mode",
    "smtp_host",
    "smtp_port",
    "smtp_user",
    "smtp_password",
    "default_domain_id",
)


def main():
    src = (os.environ.get("SOURCE_DATABASE_URL") or "").strip()
    dst = (os.environ.get("DATABASE_URL") or os.environ.get("MAILING_DATABASE_URL") or "").strip()
    if not src:
        print("SOURCE_DATABASE_URL gerekli (makropanel-db URL)")
        sys.exit(1)
    if not dst:
        print("DATABASE_URL gerekli (mikromail-db)")
        sys.exit(1)

    import psycopg2
    from psycopg2.extras import RealDictCursor

    print("Kaynak (makro):", src.split("@")[-1][:60])
    print("Hedef (mikro):", dst.split("@")[-1][:60])

    sconn = psycopg2.connect(src)
    dconn = psycopg2.connect(dst)
    sc = sconn.cursor(cursor_factory=RealDictCursor)
    dc = dconn.cursor(cursor_factory=RealDictCursor)

    sc.execute(
        "SELECT key, value FROM mail_settings WHERE key = ANY(%s)",
        (list(KEYS),),
    )
    rows = {r["key"]: (r["value"] or "") for r in sc.fetchall()}
    if not rows.get("smtp_password") and not rows.get("smtp_host"):
        print("Makro DB'de smtp ayarı yok / boş. Alibaba'dan elle set etmen lazım.")
        sys.exit(2)

    print("Makro'dan okunan:")
    for k in KEYS:
        v = rows.get(k, "")
        if k == "smtp_password":
            print(f"  {k}: len={len(v)} set={'yes' if v else 'no'}")
        else:
            print(f"  {k}: {v!r}")

    for k in KEYS:
        if k not in rows:
            continue
        dc.execute(
            """
            INSERT INTO mail_settings (key, value) VALUES (%s, %s)
            ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value
            """,
            (k, rows[k]),
        )

    # Domain SMTP şifrelerini de kopyala (varsa)
    try:
        sc.execute(
            """
            SELECT domain, from_local, from_name, smtp_password, smtp_password_enc
            FROM mail_domains ORDER BY id
            """
        )
        for d in sc.fetchall():
            pw = (d.get("smtp_password") or "").strip()
            enc = (d.get("smtp_password_enc") or "").strip()
            if not pw and not enc:
                continue
            # Mikromail'de düz şifre öncelikli — makro düz şifreyi taşı
            plain = pw if pw and not str(pw).startswith("enc:v1:") else ""
            dc.execute(
                """
                UPDATE mail_domains
                SET smtp_password = COALESCE(NULLIF(%s, ''), smtp_password),
                    smtp_password_enc = COALESCE(NULLIF(%s, ''), smtp_password_enc),
                    from_local = COALESCE(NULLIF(%s, ''), from_local),
                    from_name = COALESCE(NULLIF(%s, ''), from_name)
                WHERE domain = %s
                """,
                (plain, enc if not plain else "", d.get("from_local") or "", d.get("from_name") or "", d["domain"]),
            )
            print(f"  domain {d['domain']}: smtp copied (plain={bool(plain)})")
    except Exception as exc:
        print(f"domain copy skip: {exc}")

    # provider smtp olsun
    dc.execute(
        """
        INSERT INTO mail_settings (key, value) VALUES ('provider_mode', 'smtp')
        ON CONFLICT (key) DO UPDATE SET value = 'smtp'
        """
    )
    dconn.commit()
    print("OK — Mikromail Ayarlar güncellendi. Panelede SMTP test çalıştır.")
    sc.close()
    dc.close()
    sconn.close()
    dconn.close()


if __name__ == "__main__":
    main()
