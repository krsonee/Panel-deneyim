"""Mikromail background worker — campaigns, imports/scrub reclaim, domain warm ticks.

Run: python mailing_worker_main.py
Env: DATABASE_URL, MAILING_SECRET_KEY, same as web.
"""
from __future__ import annotations

import os
import time
from contextlib import closing
from datetime import datetime, timezone

from database import (
    execute,
    fetchall,
    fetchone,
    get_db,
    get_mail_setting,
    init_mailing_schema,
    iso,
    upsert_mail_setting,
    utcnow,
)
from mail_tenant import ensure_tenant_schema


def _tick_warm_domains(conn):
    """Takvim günü başına 1 kez warm_day / cap ilerlet (eski: her 25 sn — yanlıştı)."""
    today = datetime.now(timezone.utc).date().isoformat()
    last = (get_mail_setting(conn, "warm_tick_date", "") or "").strip()
    if last == today:
        return
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
    upsert_mail_setting(conn, "warm_tick_date", today)


def main():
    os.environ["MAILING_WORKER_EXTERNAL"] = "1"
    print("✉️  Mikromail worker starting…")
    with closing(get_db()) as conn:
        init_mailing_schema(conn)
        ensure_tenant_schema(conn)
        conn.commit()

    from mail_campaign_worker import (
        _tick_scheduled,
        ensure_campaign_scheduler,
        start_campaign_send,
    )
    from mail_scrub import ensure_mail_scrub_schema, reclaim_scrub_jobs

    ensure_campaign_scheduler()
    print("✉️  campaign scheduler on")

    while True:
        try:
            # Zamanı gelen scheduled kampanyaları da burada zorla kontrol et
            # (thread uyusa / kaçırsa diye yedek)
            try:
                _tick_scheduled()
            except Exception as tick_exc:
                print(f"⚠️  scheduled tick: {tick_exc}")
            with closing(get_db()) as conn:
                ensure_mail_scrub_schema(conn)
                # Resume queued/sending campaigns that lost in-process threads
                rows = fetchall(
                    conn,
                    """
                    SELECT id, scheduled_at, sent_count, status FROM mail_campaigns
                    WHERE status IN ('queued', 'sending')
                    ORDER BY id ASC LIMIT 15
                    """,
                ) or []
                from mail_campaign_worker import schedule_is_future
                for r in rows:
                    try:
                        cid = int(r["id"])
                        # Gelecek saatli + henüz mail gitmemiş → resume etme
                        if (
                            int(r.get("sent_count") or 0) <= 0
                            and r.get("scheduled_at")
                            and schedule_is_future(r.get("scheduled_at"))
                        ):
                            continue
                        start_campaign_send(cid)
                    except Exception as exc:
                        print(f"⚠️  resume campaign {r['id']}: {exc}")
                _tick_warm_domains(conn)
                conn.commit()
            n_scrub = reclaim_scrub_jobs(limit=2)
            if n_scrub:
                print(f"✉️  scrub reclaim started={n_scrub}")
            try:
                from mail_domain_health import tick_domain_health_once
                n_pause = tick_domain_health_once()
                if n_pause:
                    print(f"✉️  domain auto-pause count={n_pause}")
            except Exception as hexc:
                print(f"⚠️  domain health tick: {hexc}")
        except Exception as exc:
            print(f"⚠️  worker loop: {exc}")
        time.sleep(12)


if __name__ == "__main__":
    main()
