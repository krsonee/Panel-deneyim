#!/usr/bin/env python3
"""Copy mail_* tables from source DATABASE_URL to target MAILING_DATABASE_URL
and ensure tenant_id=1 (makro) + domain allocations.

Usage:
  SOURCE_DATABASE_URL=postgres://... MAILING_DATABASE_URL=postgres://... \
    python scripts/migrate_mailing_to_makromail.py

Safe to re-run for small tables; large contact tables use INSERT ... ON CONFLICT DO NOTHING
where unique keys exist.
"""
from __future__ import annotations

import os
import sys

# repo root
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

TABLES = [
    "mail_settings",
    "mail_domains",
    "mail_contact_tags",
    "mail_contacts",
    "mail_templates",
    "mail_campaigns",
    "mail_campaign_recipients",
    "mail_sends",
    "mail_ivr_rules",
    "mail_ivr_events",
    "mail_click_links",
    "mail_import_jobs",
    "mail_suppressions",
    "mail_unsub_tokens",
    "mail_audit_log",
]


def main():
    src = (os.environ.get("SOURCE_DATABASE_URL") or os.environ.get("DATABASE_URL") or "").strip()
    dst = (os.environ.get("MAILING_DATABASE_URL") or "").strip()
    if not src or not dst:
        print("SOURCE_DATABASE_URL and MAILING_DATABASE_URL required")
        sys.exit(1)
    if src == dst:
        print("Source and target are the same — running tenant ensure only on current DB")
        os.environ["DATABASE_URL"] = src
        from database import get_db, init_mailing_schema
        from mail_tenant import ensure_tenant_schema
        from contextlib import closing
        with closing(get_db()) as conn:
            init_mailing_schema(conn)
            ensure_tenant_schema(conn)
            conn.commit()
        print("OK tenant layer on same DB")
        return

    import psycopg2
    from psycopg2.extras import RealDictCursor

    print("Connecting…")
    sconn = psycopg2.connect(src)
    dconn = psycopg2.connect(dst)
    sconn.autocommit = True
    dconn.autocommit = False

    # Init schema on dest via app helpers
    os.environ["DATABASE_URL"] = dst
    os.environ["SERVICE_MODE"] = "mailing"
    from database import get_db, init_mailing_schema
    from mail_tenant import ensure_tenant_schema, encrypt_secret
    from contextlib import closing

    with closing(get_db()) as conn:
        init_mailing_schema(conn)
        ensure_tenant_schema(conn)
        conn.commit()

    sc = sconn.cursor(cursor_factory=RealDictCursor)
    dc = dconn.cursor()

    for table in TABLES:
        try:
            sc.execute(
                "SELECT EXISTS (SELECT 1 FROM information_schema.tables WHERE table_name=%s)",
                (table,),
            )
            if not sc.fetchone()["exists"]:
                print(f"skip missing {table}")
                continue
            sc.execute(f"SELECT * FROM {table}")
            rows = sc.fetchall()
            if not rows:
                print(f"{table}: 0 rows")
                continue
            cols = list(rows[0].keys())
            # Ensure tenant_id present in dest rows
            if "tenant_id" not in cols:
                cols = cols + ["tenant_id"]
                for r in rows:
                    r["tenant_id"] = 1
            else:
                for r in rows:
                    if r.get("tenant_id") in (None, 0):
                        r["tenant_id"] = 1
            placeholders = ",".join(["%s"] * len(cols))
            colsql = ",".join(cols)
            inserted = 0
            for r in rows:
                vals = [r.get(c) for c in cols]
                try:
                    dc.execute(
                        f"INSERT INTO {table} ({colsql}) VALUES ({placeholders}) ON CONFLICT DO NOTHING",
                        vals,
                    )
                    inserted += dc.rowcount
                except Exception as exc:
                    dconn.rollback()
                    print(f"  row skip {table}: {exc}")
                    dconn.commit()
                    continue
            dconn.commit()
            print(f"{table}: copied ~{inserted}/{len(rows)}")
        except Exception as exc:
            dconn.rollback()
            print(f"FAIL {table}: {exc}")

    # Encrypt plaintext smtp passwords on dest
    try:
        dc.execute("SELECT id, smtp_password, smtp_password_enc FROM mail_domains")
        for row in dc.fetchall() if False else []:
            pass
        dc.execute("SELECT id, COALESCE(smtp_password_enc,''), COALESCE(smtp_password,'') FROM mail_domains")
        for did, enc, pw in dc.fetchall():
            blob = enc or pw
            if blob and not str(blob).startswith("enc:v1:"):
                new_enc = encrypt_secret(str(blob))
                dc.execute(
                    "UPDATE mail_domains SET smtp_password_enc=%s, smtp_password=%s WHERE id=%s",
                    (new_enc, new_enc, did),
                )
        dconn.commit()
        print("encrypted domain SMTP secrets")
    except Exception as exc:
        dconn.rollback()
        print(f"encrypt skip: {exc}")

    # Re-ensure allocations
    os.environ["DATABASE_URL"] = dst
    with closing(get_db()) as conn:
        ensure_tenant_schema(conn)
        conn.commit()

    sc.close()
    dc.close()
    sconn.close()
    dconn.close()
    print("DONE — set mikromail DATABASE_URL to mailing DB and deploy.")


if __name__ == "__main__":
    main()
