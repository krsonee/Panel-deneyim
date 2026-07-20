"""MakroMail background worker — campaigns, imports/scrub reclaim, domain warm ticks.

Run: python mailing_worker_main.py
Env: DATABASE_URL, MAILING_SECRET_KEY, same as web.
"""
from __future__ import annotations

import os
import time
from contextlib import closing

from database import execute, fetchall, fetchone, get_db, init_mailing_schema, iso, utcnow
from mail_tenant import ensure_tenant_schema


def _tick_warm_domains(conn):
    """Advance warm_day slowly for domains in warming state (cap ramp helper)."""
    rows = fetchall(
        conn,
        """
        SELECT id, warm_day, daily_cap, hourly_cap FROM mail_domains
        WHERE COALESCE(warm_status, 'cold') = 'warming'
        ORDER BY id ASC LIMIT 50
        """,
    ) or []
    for r in rows:
        day = int(r["warm_day"] or 0) + 1
        # Simple ramp: daily_cap grows toward 5000 over ~30 days
        base = 50
        target = max(int(r["daily_cap"] or 500), base)
        new_cap = min(5000, base + day * max(20, target // 30))
        execute(
            conn,
            "UPDATE mail_domains SET warm_day = ?, daily_cap = ? WHERE id = ?",
            (day, new_cap, r["id"]),
        )
        if day >= 30 and new_cap >= 2000:
            execute(
                conn,
                "UPDATE mail_domains SET warm_status = 'warm' WHERE id = ?",
                (r["id"],),
            )


def main():
    os.environ["MAILING_WORKER_EXTERNAL"] = "1"
    print("✉️  MakroMail worker starting…")
    with closing(get_db()) as conn:
        init_mailing_schema(conn)
        ensure_tenant_schema(conn)
        conn.commit()

    from mail_campaign_worker import ensure_campaign_scheduler, start_campaign_send
    from mail_scrub import ensure_mail_scrub_schema

    ensure_campaign_scheduler()
    print("✉️  campaign scheduler on")

    while True:
        try:
            with closing(get_db()) as conn:
                ensure_mail_scrub_schema(conn)
                # Resume queued campaigns that lost in-process threads
                rows = fetchall(
                    conn,
                    """
                    SELECT id FROM mail_campaigns
                    WHERE status IN ('queued', 'sending')
                    ORDER BY id ASC LIMIT 10
                    """,
                ) or []
                for r in rows:
                    try:
                        start_campaign_send(int(r["id"]))
                    except Exception as exc:
                        print(f"⚠️  resume campaign {r['id']}: {exc}")
                _tick_warm_domains(conn)
                conn.commit()
        except Exception as exc:
            print(f"⚠️  worker loop: {exc}")
        time.sleep(25)


if __name__ == "__main__":
    main()
