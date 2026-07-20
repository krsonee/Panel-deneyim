"""Kampanya arka plan gönderim worker — zamanlama, hız limiti, iptal, ilerleme."""

from __future__ import annotations

import threading
import time
from contextlib import closing
from datetime import datetime, timezone

from database import execute, fetchall, fetchone, get_db, get_mail_setting, iso, scalar, utcnow
from mail_delivery import deliver_mail

_lock = threading.Lock()
_running = set()
_scheduler_started = False


def _parse_iso(value):
    text = (value or "").strip()
    if not text:
        return None
    try:
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        dt = datetime.fromisoformat(text)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt
    except ValueError:
        return None


def is_campaign_running(campaign_id):
    with _lock:
        return int(campaign_id) in _running


def start_campaign_send(campaign_id):
    """Kampanyayı arka planda gönderime başlat (idempotent)."""
    cid = int(campaign_id)
    with _lock:
        if cid in _running:
            return False
        _running.add(cid)
    t = threading.Thread(target=_run_campaign_job, args=(cid,), daemon=True, name=f"mail-camp-{cid}")
    t.start()
    return True


def ensure_campaign_scheduler():
    """Zamanlanmış kampanyaları periyodik başlatır."""
    global _scheduler_started
    with _lock:
        if _scheduler_started:
            return
        _scheduler_started = True
    t = threading.Thread(target=_scheduler_loop, daemon=True, name="mail-camp-scheduler")
    t.start()


def _scheduler_loop():
    while True:
        try:
            _tick_scheduled()
        except Exception as exc:
            print(f"⚠️  mail campaign scheduler: {exc}")
        time.sleep(20)


def _tick_scheduled():
    now = utcnow()
    now_iso = iso(now)
    with closing(get_db()) as conn:
        rows = fetchall(
            conn,
            """
            SELECT id, scheduled_at, status FROM mail_campaigns
            WHERE status IN ('scheduled', 'queued')
            ORDER BY id ASC
            LIMIT 20
            """,
        )
        due = []
        for r in rows:
            cid = r["id"]
            if is_campaign_running(cid):
                continue
            if r["status"] == "queued":
                due.append(cid)
                continue
            sched = _parse_iso(r.get("scheduled_at"))
            if sched and sched <= now:
                due.append(cid)
            elif not sched and r["status"] == "scheduled":
                # Zaman yoksa hemen başlat
                due.append(cid)
        for cid in due:
            execute(
                conn,
                "UPDATE mail_campaigns SET status = 'queued', updated_at = ? WHERE id = ? AND status IN ('scheduled', 'queued')",
                (now_iso, cid),
            )
        if due:
            conn.commit()
    for cid in due:
        start_campaign_send(cid)


def _campaign_cancelled(conn, campaign_id):
    row = fetchone(conn, "SELECT status FROM mail_campaigns WHERE id = ?", (campaign_id,))
    return not row or row["status"] in ("cancelling", "cancelled")


def _campaign_paused(conn, campaign_id):
    row = fetchone(conn, "SELECT status FROM mail_campaigns WHERE id = ?", (campaign_id,))
    return bool(row and row["status"] == "paused")


def _run_campaign_job(campaign_id):
    try:
        _process_campaign(campaign_id)
    except Exception as exc:
        try:
            with closing(get_db()) as conn:
                execute(
                    conn,
                    """
                    UPDATE mail_campaigns
                    SET status = 'error', error = ?, finished_at = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (str(exc)[:500], iso(utcnow()), iso(utcnow()), campaign_id),
                )
                conn.commit()
        except Exception:
            pass
        print(f"⚠️  mail campaign #{campaign_id} failed: {exc}")
    finally:
        with _lock:
            _running.discard(int(campaign_id))


def _process_campaign(campaign_id):
    # Lazy import — circular: mailing_routes helpers
    from mailing_routes import _inject_tracking, _plain_to_html, _render_template

    now = iso(utcnow())
    with closing(get_db()) as conn:
        camp = fetchone(conn, "SELECT * FROM mail_campaigns WHERE id = ?", (campaign_id,))
        if not camp:
            return
        camp = dict(camp) if not isinstance(camp, dict) else camp
        if camp["status"] in ("done", "cancelled", "error"):
            return
        tpl = fetchone(conn, "SELECT * FROM mail_templates WHERE id = ?", (camp["template_id"],))
        if not tpl:
            execute(
                conn,
                "UPDATE mail_campaigns SET status = 'error', error = ?, finished_at = ?, updated_at = ? WHERE id = ?",
                ("Şablon bulunamadı.", now, now, campaign_id),
            )
            conn.commit()
            return
        tpl = dict(tpl) if not isinstance(tpl, dict) else tpl

        total = scalar(
            conn,
            "SELECT COUNT(*) FROM mail_campaign_recipients WHERE campaign_id = ?",
            (campaign_id,),
        ) or 0
        execute(
            conn,
            """
            UPDATE mail_campaigns
            SET status = 'sending', started_at = COALESCE(started_at, ?),
                queued_at = COALESCE(queued_at, ?), total_count = ?, error = '', updated_at = ?
            WHERE id = ?
            """,
            (now, now, total, now, campaign_id),
        )
        conn.commit()

        rate = int(camp.get("rate_per_minute") or 0)
        # Stub'da hız limiti gerekmez; SMTP'te varsayılan 120/dk
        mode = (get_mail_setting(conn, "provider_mode", "stub") or "stub").strip().lower()
        if mode != "smtp":
            rate = max(rate, 6000)  # stub: çok hızlı (batch simülasyon)
        delay = (60.0 / rate) if rate and rate > 0 else 0.0

        batch_size = 40
        sent_count = int(camp.get("sent_count") or 0)
        failed_count = int(camp.get("failed_count") or 0)
        skipped_count = int(camp.get("skipped_count") or 0)

        # Domain bazlı hız (varsa kampanya hızından düşük olan uygulanır)
        try:
            drow = fetchone(conn, "SELECT rate_per_minute FROM mail_domains WHERE id = ?", (camp.get("domain_id"),))
            dom_rate = int((drow or {}).get("rate_per_minute") or 0) if drow else 0
            if dom_rate > 0:
                rate = min(rate, dom_rate) if rate > 0 else dom_rate
                delay = (60.0 / rate) if rate > 0 else delay
        except Exception:
            pass

        while True:
            if _campaign_cancelled(conn, campaign_id):
                execute(
                    conn,
                    """
                    UPDATE mail_campaigns
                    SET status = 'cancelled', finished_at = ?, updated_at = ?,
                        sent_count = ?, failed_count = ?, skipped_count = ?
                    WHERE id = ?
                    """,
                    (iso(utcnow()), iso(utcnow()), sent_count, failed_count, skipped_count, campaign_id),
                )
                conn.commit()
                return
            if _campaign_paused(conn, campaign_id):
                execute(
                    conn,
                    """
                    UPDATE mail_campaigns
                    SET sent_count = ?, failed_count = ?, skipped_count = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (sent_count, failed_count, skipped_count, iso(utcnow()), campaign_id),
                )
                conn.commit()
                return

            recipients = fetchall(
                conn,
                """
                SELECT r.id AS recipient_id, r.contact_id, c.email, c.phone, c.name, c.unsubscribed
                FROM mail_campaign_recipients r
                JOIN mail_contacts c ON c.id = r.contact_id
                WHERE r.campaign_id = ? AND r.status = 'pending'
                ORDER BY r.id ASC
                LIMIT ?
                """,
                (campaign_id, batch_size),
            )
            if not recipients:
                break

            for rec in recipients:
                if _campaign_cancelled(conn, campaign_id) or _campaign_paused(conn, campaign_id):
                    break
                rec = dict(rec)
                now = iso(utcnow())
                if rec.get("unsubscribed"):
                    execute(
                        conn,
                        "UPDATE mail_campaign_recipients SET status = 'skipped' WHERE id = ?",
                        (rec["recipient_id"],),
                    )
                    skipped_count += 1
                    continue

                contact = {
                    "name": rec.get("name") or "",
                    "email": rec.get("email") or "",
                    "phone": rec.get("phone") or "",
                }
                subject = _render_template(tpl["subject"], contact)
                html_body = _render_template(
                    tpl.get("html_body") or _plain_to_html(tpl.get("text_body") or ""), contact
                )
                text_body = _render_template(tpl.get("text_body") or "", contact)
                send_id, status, err = deliver_mail(
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
                    html_body=html_body,
                    text_body=text_body,
                    inject_tracking=_inject_tracking,
                )
                recip_status = status if status in ("simulated", "sent", "queued", "failed", "skipped") else "failed"
                execute(
                    conn,
                    "UPDATE mail_campaign_recipients SET status = ?, send_id = ? WHERE id = ?",
                    (recip_status, send_id, rec["recipient_id"]),
                )
                if status in ("simulated", "sent"):
                    sent_count += 1
                    try:
                        from mail_tenant import bump_usage
                        tid = camp.get("tenant_id")
                        if tid:
                            bump_usage(conn, int(tid), sent=1)
                    except Exception:
                        pass
                elif status == "skipped":
                    skipped_count += 1
                elif status == "failed":
                    failed_count += 1
                    try:
                        from mail_tenant import bump_usage
                        tid = camp.get("tenant_id")
                        if tid:
                            bump_usage(conn, int(tid), failed=1)
                    except Exception:
                        pass
                else:
                    failed_count += 1

                execute(
                    conn,
                    """
                    UPDATE mail_campaigns
                    SET sent_count = ?, failed_count = ?, skipped_count = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (sent_count, failed_count, skipped_count, now, campaign_id),
                )
                conn.commit()
                if delay > 0:
                    time.sleep(delay)

            if _campaign_cancelled(conn, campaign_id):
                execute(
                    conn,
                    """
                    UPDATE mail_campaigns
                    SET status = 'cancelled', finished_at = ?, updated_at = ?,
                        sent_count = ?, failed_count = ?, skipped_count = ?
                    WHERE id = ?
                    """,
                    (iso(utcnow()), iso(utcnow()), sent_count, failed_count, skipped_count, campaign_id),
                )
                conn.commit()
                return
            if _campaign_paused(conn, campaign_id):
                execute(
                    conn,
                    """
                    UPDATE mail_campaigns
                    SET sent_count = ?, failed_count = ?, skipped_count = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (sent_count, failed_count, skipped_count, iso(utcnow()), campaign_id),
                )
                conn.commit()
                return

        now = iso(utcnow())
        execute(
            conn,
            """
            UPDATE mail_campaigns
            SET status = 'done', finished_at = ?, updated_at = ?,
                sent_count = ?, failed_count = ?, skipped_count = ?, error = ''
            WHERE id = ?
            """,
            (now, now, sent_count, failed_count, skipped_count, campaign_id),
        )
        conn.commit()
