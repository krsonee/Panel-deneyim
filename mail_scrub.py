"""Liste temizleme — syntax / disposable / MX / SMTP RCPT doğrulama."""

from __future__ import annotations

import json
import random
import re
import smtplib
import socket
import string
import threading
import time
from contextlib import closing, suppress
from email.utils import parseaddr

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
    uses_postgres,
    utcnow,
)

EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")

ROLE_LOCALS = frozenset({
    "info", "noreply", "no-reply", "mailer-daemon", "postmaster", "abuse",
    "admin", "administrator", "support", "help", "sales", "marketing",
    "contact", "webmaster", "hostmaster", "root", "null", "bounce",
    "newsletter", "subscribe", "unsubscribe", "donotreply", "do-not-reply",
})

# Yaygın tek-kullanımlık / geçici mail sağlayıcıları (kısa liste — genişletilebilir)
DISPOSABLE_DOMAINS = frozenset({
    "mailinator.com", "guerrillamail.com", "guerrillamail.de", "10minutemail.com",
    "tempmail.com", "temp-mail.org", "throwaway.email", "yopmail.com",
    "sharklasers.com", "trashmail.com", "getnada.com", "maildrop.cc",
    "dispostable.com", "fakeinbox.com", "mailnesia.com", "moakt.com",
    "tempail.com", "emailondeck.com", "mintemail.com", "mytemp.email",
    "discard.email", "mailcatch.com", "spamgourmet.com", "trash-mail.com",
})

VERIFY_TAGS = {
    "valid": "mail_valid",
    "invalid": "mail_invalid",
    "unknown": "mail_unknown",
    "catch_all": "mail_catch_all",
    "disposable": "mail_disposable",
    "role": "mail_role",
    "mx_ok": "mail_mx_ok",
}

_SCRUB_LOCK = threading.Lock()
_SCRUB_RUNNING: set[int] = set()


def _add_contact_col(conn, col_sql: str) -> None:
    """Kolon yoksa ekle; varsa / hata olursa yut (Postgres + SQLite)."""
    try:
        execute(conn, f"ALTER TABLE mail_contacts ADD COLUMN {col_sql}")
        conn.commit()
    except Exception:
        with suppress(Exception):
            conn.rollback()


def ensure_mail_scrub_schema(conn):
    if uses_postgres():
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS mail_scrub_jobs (
                id SERIAL PRIMARY KEY,
                status TEXT NOT NULL DEFAULT 'pending',
                scope TEXT NOT NULL DEFAULT 'filter',
                tag_filter TEXT NOT NULL DEFAULT '',
                contact_ids_json TEXT NOT NULL DEFAULT '[]',
                total INTEGER NOT NULL DEFAULT 0,
                processed INTEGER NOT NULL DEFAULT 0,
                valid_count INTEGER NOT NULL DEFAULT 0,
                invalid_count INTEGER NOT NULL DEFAULT 0,
                unknown_count INTEGER NOT NULL DEFAULT 0,
                catch_all_count INTEGER NOT NULL DEFAULT 0,
                disposable_count INTEGER NOT NULL DEFAULT 0,
                role_count INTEGER NOT NULL DEFAULT 0,
                suppressed_count INTEGER NOT NULL DEFAULT 0,
                skipped_count INTEGER NOT NULL DEFAULT 0,
                error TEXT NOT NULL DEFAULT '',
                last_contact_id INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
        )
    else:
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS mail_scrub_jobs (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                status TEXT NOT NULL DEFAULT 'pending',
                scope TEXT NOT NULL DEFAULT 'filter',
                tag_filter TEXT NOT NULL DEFAULT '',
                contact_ids_json TEXT NOT NULL DEFAULT '[]',
                total INTEGER NOT NULL DEFAULT 0,
                processed INTEGER NOT NULL DEFAULT 0,
                valid_count INTEGER NOT NULL DEFAULT 0,
                invalid_count INTEGER NOT NULL DEFAULT 0,
                unknown_count INTEGER NOT NULL DEFAULT 0,
                catch_all_count INTEGER NOT NULL DEFAULT 0,
                disposable_count INTEGER NOT NULL DEFAULT 0,
                role_count INTEGER NOT NULL DEFAULT 0,
                suppressed_count INTEGER NOT NULL DEFAULT 0,
                skipped_count INTEGER NOT NULL DEFAULT 0,
                error TEXT NOT NULL DEFAULT '',
                last_contact_id INTEGER NOT NULL DEFAULT 0,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            )
            """,
        )
    # Eski tablolara last_contact_id
    try:
        execute(conn, "ALTER TABLE mail_scrub_jobs ADD COLUMN last_contact_id INTEGER NOT NULL DEFAULT 0")
        conn.commit()
    except Exception:
        with suppress(Exception):
            conn.rollback()
    # verify kolonları — tek tek (biri fail ederse hepsi rollback olmasın)
    _add_contact_col(conn, "verify_status TEXT NOT NULL DEFAULT ''")
    _add_contact_col(conn, "verify_detail TEXT NOT NULL DEFAULT ''")
    _add_contact_col(conn, "verified_at TEXT")
    try:
        conn.commit()
    except Exception:
        pass
    # Varsayılan ayarlar (yoksa)
    defaults = {
        "scrub_smtp_verify": "1",
        "scrub_rate_per_minute": "30",
        "scrub_auto_suppress_invalid": "1",
        "scrub_suppress_disposable": "1",
        "scrub_suppress_role": "0",
        "scrub_campaign_only_valid": "0",
        "scrub_skip_hours": "168",
        "scrub_mail_from": "",
    }
    for key, val in defaults.items():
        if get_mail_setting(conn, key, None) is None:
            upsert_mail_setting(conn, key, val)
    try:
        conn.commit()
    except Exception:
        pass


def cancel_active_scrub_jobs(reason="Panel yeniden başladı — aktif temizlik durduruldu."):
    now = iso(utcnow())
    with closing(get_db()) as conn:
        rows = fetchall(
            conn,
            "SELECT id FROM mail_scrub_jobs WHERE status IN ('pending', 'running', 'cancelling')",
        ) or []
        for row in rows:
            execute(
                conn,
                "UPDATE mail_scrub_jobs SET status = 'cancelled', error = ?, updated_at = ? WHERE id = ?",
                ((reason or "")[:500], now, row["id"]),
            )
        conn.commit()


def scrub_settings(conn=None):
    close = False
    if conn is None:
        conn = get_db()
        close = True
    try:
        def g(key, default):
            return (get_mail_setting(conn, key, default) or default).strip()

        rate = 30
        try:
            rate = max(1, min(int(g("scrub_rate_per_minute", "30") or 30), 600))
        except (TypeError, ValueError):
            rate = 30
        skip_h = 168
        try:
            skip_h = max(0, min(int(g("scrub_skip_hours", "168") or 168), 24 * 90))
        except (TypeError, ValueError):
            skip_h = 168
        return {
            "scrub_smtp_verify": g("scrub_smtp_verify", "1") in ("1", "true", "yes", "on"),
            "scrub_rate_per_minute": rate,
            "scrub_auto_suppress_invalid": g("scrub_auto_suppress_invalid", "1") in ("1", "true", "yes", "on"),
            "scrub_suppress_disposable": g("scrub_suppress_disposable", "1") in ("1", "true", "yes", "on"),
            "scrub_suppress_role": g("scrub_suppress_role", "0") in ("1", "true", "yes", "on"),
            "scrub_campaign_only_valid": g("scrub_campaign_only_valid", "0") in ("1", "true", "yes", "on"),
            "scrub_skip_hours": skip_h,
            "scrub_mail_from": g("scrub_mail_from", ""),
        }
    finally:
        if close:
            with suppress(Exception):
                conn.close()


def _mx_hosts(domain: str) -> list[str]:
    domain = (domain or "").strip().lower().rstrip(".")
    if not domain:
        return []
    try:
        import dns.resolver  # type: ignore

        answers = dns.resolver.resolve(domain, "MX")
        pairs = []
        for r in answers:
            host = str(r.exchange).rstrip(".").lower()
            if host:
                pairs.append((int(r.preference), host))
        pairs.sort(key=lambda x: x[0])
        return [h for _, h in pairs]
    except Exception:
        pass
    # Fallback: A/AAAA kaydı varsa domain'i host say
    try:
        infos = socket.getaddrinfo(domain, 25, type=socket.SOCK_STREAM)
        if infos:
            return [domain]
    except Exception:
        pass
    return []


def _smtp_probe(email: str, mx_hosts: list[str], mail_from: str, timeout: float = 12.0) -> tuple[str, str]:
    """Döner: (status, detail) — valid|invalid|unknown|catch_all"""
    mail_from = (mail_from or "probe@localhost").strip()
    last_detail = "no_mx_connect"
    for host in mx_hosts[:3]:
        try:
            with smtplib.SMTP(timeout=timeout) as smtp:
                smtp.connect(host, 25)
                smtp.ehlo_or_helo_if_needed()
                code, _ = smtp.mail(mail_from)
                if code not in (250, 251):
                    last_detail = f"mail_from_{code}"
                    continue
                code, msg = smtp.rcpt(email)
                msg_s = (msg.decode("utf-8", "ignore") if isinstance(msg, bytes) else str(msg or ""))[:180]
                if code in (250, 251):
                    # Catch-all kontrolü
                    local = email.split("@", 1)[0]
                    domain = email.split("@", 1)[1]
                    rand_local = "xx" + "".join(random.choices(string.ascii_lowercase + string.digits, k=12))
                    if rand_local == local:
                        rand_local = rand_local + "z"
                    code2, _ = smtp.rcpt(f"{rand_local}@{domain}")
                    with suppress(Exception):
                        smtp.rset()
                    if code2 in (250, 251):
                        return "catch_all", f"rcpt_ok_catchall @{host}"
                    return "valid", f"rcpt_ok @{host}"
                if code in (550, 551, 552, 553, 554):
                    return "invalid", f"rcpt_{code} @{host}: {msg_s}"
                last_detail = f"rcpt_{code} @{host}: {msg_s}"
        except (smtplib.SMTPServerDisconnected, smtplib.SMTPConnectError, smtplib.SMTPHeloError,
                TimeoutError, socket.timeout, ConnectionError, OSError) as exc:
            last_detail = f"{type(exc).__name__}:{str(exc)[:120]}"
            continue
        except Exception as exc:
            last_detail = f"{type(exc).__name__}:{str(exc)[:120]}"
            continue
    return "unknown", last_detail


def verify_email(email: str, *, smtp_verify: bool = True, mail_from: str = "") -> dict:
    """Tek adres doğrula. status: valid|invalid|unknown|catch_all|disposable|role|mx_ok"""
    raw = (email or "").strip()
    _, addr = parseaddr(raw)
    addr = (addr or raw).strip().lower()
    if not addr or not EMAIL_RE.match(addr) or ".." in addr or addr.startswith(".") or addr.endswith("."):
        return {"email": addr, "status": "invalid", "detail": "bad_syntax"}

    local, _, domain = addr.partition("@")
    if not local or not domain or "." not in domain:
        return {"email": addr, "status": "invalid", "detail": "bad_parts"}

    if domain in DISPOSABLE_DOMAINS:
        return {"email": addr, "status": "disposable", "detail": "disposable_domain"}

    if local.lower() in ROLE_LOCALS:
        return {"email": addr, "status": "role", "detail": f"role:{local}"}

    mx = _mx_hosts(domain)
    if not mx:
        return {"email": addr, "status": "invalid", "detail": "no_mx"}

    if not smtp_verify:
        return {"email": addr, "status": "mx_ok", "detail": f"mx:{mx[0]}"}

    status, detail = _smtp_probe(addr, mx, mail_from or f"probe@{domain}")
    return {"email": addr, "status": status, "detail": detail}


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


def _set_verify_tags(conn, contact_id, status, now):
    row = fetchone(conn, "SELECT tags FROM mail_contacts WHERE id = ?", (contact_id,))
    if not row:
        return
    tags = _parse_tags(row["tags"])
    # Eski scrub etiketlerini temizle
    scrub_set = set(VERIFY_TAGS.values())
    tags = [t for t in tags if t not in scrub_set]
    tag = VERIFY_TAGS.get(status)
    if tag and tag not in tags:
        tags.append(tag)
    execute(
        conn,
        "UPDATE mail_contacts SET tags = ?, updated_at = ? WHERE id = ?",
        (json.dumps(tags, ensure_ascii=False), now, contact_id),
    )
    if tag:
        exists = scalar(conn, "SELECT COUNT(*) FROM mail_contact_tags WHERE name = ?", (tag,))
        if not exists:
            insert_returning_id(
                conn,
                "INSERT INTO mail_contact_tags (name, created_at) VALUES (?, ?)",
                (tag, now),
            )


def _apply_result(conn, contact_id, email, result, settings, now):
    status = result["status"]
    detail = (result.get("detail") or "")[:240]
    execute(
        conn,
        """
        UPDATE mail_contacts
        SET verify_status = ?, verify_detail = ?, verified_at = ?, updated_at = ?
        WHERE id = ?
        """,
        (status, detail, now, now, contact_id),
    )
    _set_verify_tags(conn, contact_id, status, now)

    suppressed = False
    from mail_ops import suppress_email

    if status == "invalid" and settings["scrub_auto_suppress_invalid"]:
        suppress_email(conn, email, reason="invalid", source="scrub")
        suppressed = True
    elif status == "disposable" and settings["scrub_suppress_disposable"]:
        suppress_email(conn, email, reason="disposable", source="scrub")
        suppressed = True
    elif status == "role" and settings["scrub_suppress_role"]:
        suppress_email(conn, email, reason="role", source="scrub")
        suppressed = True
    return suppressed


def _job_cancelled(conn, job_id) -> bool:
    row = fetchone(conn, "SELECT status FROM mail_scrub_jobs WHERE id = ?", (job_id,))
    if not row:
        return True
    return (row["status"] or "") in ("cancelling", "cancelled")


def _row_get(row, key, default=None):
    if row is None:
        return default
    if isinstance(row, dict):
        return row.get(key, default)
    try:
        return row[key]
    except Exception:
        return default


def _external_worker_mode() -> bool:
    import os
    return (os.environ.get("MAILING_WORKER_EXTERNAL") or "").strip().lower() in (
        "1", "true", "yes", "on",
    )


def _run_scrub_job(job_id: int):
    with _SCRUB_LOCK:
        if job_id in _SCRUB_RUNNING:
            return
        _SCRUB_RUNNING.add(job_id)
    try:
        _process_scrub_job(job_id)
    finally:
        with _SCRUB_LOCK:
            _SCRUB_RUNNING.discard(job_id)


def reclaim_scrub_jobs(limit: int = 3) -> int:
    """Worker: pending/yarım kalmış scrub işlerini bu process'te çalıştır."""
    started = 0
    with closing(get_db()) as conn:
        ensure_mail_scrub_schema(conn)
        rows = fetchall(
            conn,
            """
            SELECT id, status, updated_at FROM mail_scrub_jobs
            WHERE status IN ('pending', 'running')
            ORDER BY id ASC LIMIT ?
            """,
            (max(1, int(limit)),),
        ) or []
        conn.commit()
    for row in rows:
        jid = int(row["id"])
        with _SCRUB_LOCK:
            if jid in _SCRUB_RUNNING:
                continue
        t = threading.Thread(target=_run_scrub_job, args=(jid,), daemon=True, name=f"mail-scrub-{jid}")
        t.start()
        started += 1
    return started


def _process_scrub_job(job_id: int):
    now = iso(utcnow())
    with closing(get_db()) as conn:
        ensure_mail_scrub_schema(conn)
        job = fetchone(conn, "SELECT * FROM mail_scrub_jobs WHERE id = ?", (job_id,))
        if not job:
            return
        status = (_row_get(job, "status") or "").strip()
        if status in ("cancelled", "done", "error"):
            return
        execute(
            conn,
            "UPDATE mail_scrub_jobs SET status = 'running', error = '', updated_at = ? WHERE id = ?",
            (now, job_id),
        )
        conn.commit()
        settings = scrub_settings(conn)
        mail_from = settings["scrub_mail_from"]
        if not mail_from:
            mail_from = (get_mail_setting(conn, "smtp_user", "") or "").strip()
        if not mail_from:
            mail_from = "noreply@localhost"

        selected_ids = []
        try:
            selected_ids = json.loads(_row_get(job, "contact_ids_json") or "[]")
        except Exception:
            selected_ids = []
        selected_ids = sorted({
            int(x) for x in selected_ids
            if isinstance(x, int) or (isinstance(x, str) and str(x).isdigit())
        })
        tag_filter = (_row_get(job, "tag_filter") or "").strip()
        resume_after = int(_row_get(job, "last_contact_id") or 0)
        processed = int(_row_get(job, "processed") or 0)
        counts = {
            "valid": int(_row_get(job, "valid_count") or 0),
            "invalid": int(_row_get(job, "invalid_count") or 0),
            "unknown": int(_row_get(job, "unknown_count") or 0),
            "catch_all": int(_row_get(job, "catch_all_count") or 0),
            "disposable": int(_row_get(job, "disposable_count") or 0),
            "role": int(_row_get(job, "role_count") or 0),
            "mx_ok": 0,
        }
        # valid_count daha önce mx_ok ile birleşik yazılmış olabilir
        suppressed_n = int(_row_get(job, "suppressed_count") or 0)
        skipped_n = int(_row_get(job, "skipped_count") or 0)
        total = int(_row_get(job, "total") or 0)

        if selected_ids:
            total = len(selected_ids)
            if resume_after:
                selected_ids = [i for i in selected_ids if i > resume_after]
        elif not total:
            clauses = ["unsubscribed = 0"]
            params = []
            if tag_filter:
                clauses.append("tags LIKE ?")
                params.append(f'%"{tag_filter}"%')
            where = " AND ".join(clauses)
            try:
                total = int(scalar(conn, f"SELECT COUNT(*) FROM mail_contacts WHERE {where}", tuple(params)) or 0)
            except Exception:
                total = 0

        execute(
            conn,
            "UPDATE mail_scrub_jobs SET total = ?, updated_at = ? WHERE id = ?",
            (total, iso(utcnow()), job_id),
        )
        conn.commit()

    interval = 60.0 / float(settings["scrub_rate_per_minute"] or 30)
    skip_hours = settings["scrub_skip_hours"]
    batch_size = 200
    last_contact_id = resume_after
    row_errors = 0

    def _iter_batches():
        nonlocal last_contact_id
        if selected_ids:
            for i in range(0, len(selected_ids), batch_size):
                chunk = selected_ids[i:i + batch_size]
                with closing(get_db()) as conn:
                    ph = ",".join(["?"] * len(chunk))
                    rows = fetchall(
                        conn,
                        f"SELECT id, email, verified_at, verify_status FROM mail_contacts WHERE id IN ({ph}) ORDER BY id ASC",
                        tuple(chunk),
                    ) or []
                yield rows
            return
        cursor = last_contact_id
        while True:
            with closing(get_db()) as conn:
                clauses = ["unsubscribed = 0", "id > ?"]
                params = [cursor]
                if tag_filter:
                    clauses.append("tags LIKE ?")
                    params.append(f'%"{tag_filter}"%')
                where = " AND ".join(clauses)
                rows = fetchall(
                    conn,
                    f"SELECT id, email, verified_at, verify_status FROM mail_contacts WHERE {where} ORDER BY id ASC LIMIT ?",
                    tuple(params) + (batch_size,),
                ) or []
            if not rows:
                break
            cursor = int(rows[-1]["id"])
            yield rows

    try:
        for rows in _iter_batches():
            for row in rows:
                cid = int(row["id"])
                email = (row["email"] or "").strip().lower()
                verified_at = _row_get(row, "verified_at")
                verify_status = _row_get(row, "verify_status")

                with closing(get_db()) as conn:
                    if _job_cancelled(conn, job_id):
                        execute(
                            conn,
                            "UPDATE mail_scrub_jobs SET status = 'cancelled', updated_at = ? WHERE id = ?",
                            (iso(utcnow()), job_id),
                        )
                        conn.commit()
                        return

                # Skip yakın zamanda doğrulanmışlar (DB bağlantısı tutmadan)
                if skip_hours > 0 and verified_at and verify_status:
                    try:
                        from datetime import datetime, timezone, timedelta
                        raw_ts = str(verified_at).replace("Z", "+00:00")
                        if "T" not in raw_ts and " " in raw_ts:
                            raw_ts = raw_ts.replace(" ", "T", 1)
                        vt = datetime.fromisoformat(raw_ts)
                        if vt.tzinfo is None:
                            vt = vt.replace(tzinfo=timezone.utc)
                        if datetime.now(timezone.utc) - vt < timedelta(hours=skip_hours):
                            skipped_n += 1
                            processed += 1
                            last_contact_id = cid
                            if processed % 50 == 0:
                                with closing(get_db()) as conn:
                                    _update_job_progress(
                                        conn, job_id, processed, counts, suppressed_n, skipped_n, last_contact_id
                                    )
                                    conn.commit()
                            continue
                    except Exception:
                        pass

                t0 = time.monotonic()
                try:
                    result = verify_email(
                        email,
                        smtp_verify=settings["scrub_smtp_verify"],
                        mail_from=mail_from,
                    )
                except Exception as verify_exc:
                    result = {"email": email, "status": "unknown", "detail": f"verify_exc:{verify_exc}"[:200]}

                try:
                    with closing(get_db()) as conn:
                        now = iso(utcnow())
                        if _apply_result(conn, cid, email, result, settings, now):
                            suppressed_n += 1
                        st = result.get("status") or "unknown"
                        if st in counts:
                            counts[st] += 1
                        else:
                            counts["unknown"] += 1
                        processed += 1
                        last_contact_id = cid
                        if processed % 10 == 0 or st == "invalid":
                            _update_job_progress(
                                conn, job_id, processed, counts, suppressed_n, skipped_n, last_contact_id
                            )
                        conn.commit()
                except Exception as row_exc:
                    row_errors += 1
                    with suppress(Exception):
                        with closing(get_db()) as conn:
                            execute(
                                conn,
                                "UPDATE mail_scrub_jobs SET error = ?, last_contact_id = ?, updated_at = ? WHERE id = ?",
                                (f"row#{cid}: {row_exc}"[:500], cid, iso(utcnow()), job_id),
                            )
                            conn.commit()
                    # Şema eksikse bir kez daha dene, sonra devam
                    if row_errors <= 2:
                        with suppress(Exception):
                            with closing(get_db()) as conn:
                                ensure_mail_scrub_schema(conn)
                                conn.commit()
                    if row_errors >= 25:
                        raise RuntimeError(f"Çok fazla satır hatası ({row_errors}). Son: {row_exc}") from row_exc
                    processed += 1
                    last_contact_id = cid
                    continue

                if settings["scrub_smtp_verify"]:
                    elapsed = time.monotonic() - t0
                    sleep_for = interval - elapsed
                    if sleep_for > 0:
                        time.sleep(sleep_for)
                else:
                    # MX-only: hafif throttle
                    elapsed = time.monotonic() - t0
                    sleep_for = min(interval, 0.05) - elapsed
                    if sleep_for > 0:
                        time.sleep(sleep_for)

        with closing(get_db()) as conn:
            if total and processed > total:
                total = processed
            elif not total:
                total = processed
            execute(
                conn,
                "UPDATE mail_scrub_jobs SET total = ? WHERE id = ?",
                (total, job_id),
            )
            _update_job_progress(conn, job_id, processed, counts, suppressed_n, skipped_n, last_contact_id)
            execute(
                conn,
                "UPDATE mail_scrub_jobs SET status = 'done', error = ?, updated_at = ? WHERE id = ?",
                ((f"row_errors={row_errors}" if row_errors else ""), iso(utcnow()), job_id),
            )
            conn.commit()
    except Exception as exc:
        with closing(get_db()) as conn:
            execute(
                conn,
                """
                UPDATE mail_scrub_jobs SET
                    status = 'error', error = ?, processed = ?, last_contact_id = ?, updated_at = ?
                WHERE id = ?
                """,
                (str(exc)[:500], processed, last_contact_id, iso(utcnow()), job_id),
            )
            conn.commit()


def _update_job_progress(conn, job_id, processed, counts, suppressed_n, skipped_n, last_contact_id=0):
    execute(
        conn,
        """
        UPDATE mail_scrub_jobs SET
            processed = ?,
            valid_count = ?,
            invalid_count = ?,
            unknown_count = ?,
            catch_all_count = ?,
            disposable_count = ?,
            role_count = ?,
            suppressed_count = ?,
            skipped_count = ?,
            last_contact_id = ?,
            updated_at = ?
        WHERE id = ?
        """,
        (
            processed,
            counts.get("valid", 0) + counts.get("mx_ok", 0),
            counts.get("invalid", 0),
            counts.get("unknown", 0),
            counts.get("catch_all", 0),
            counts.get("disposable", 0),
            counts.get("role", 0),
            suppressed_n,
            skipped_n,
            int(last_contact_id or 0),
            iso(utcnow()),
            job_id,
        ),
    )


def start_scrub_job(*, tag_filter="", contact_ids=None, scope="filter") -> int:
    now = iso(utcnow())
    ids = list(contact_ids or [])
    ids_json = json.dumps([int(x) for x in ids], ensure_ascii=False)
    with closing(get_db()) as conn:
        ensure_mail_scrub_schema(conn)
        # Aynı anda tek aktif iş
        active = scalar(
            conn,
            "SELECT COUNT(*) FROM mail_scrub_jobs WHERE status IN ('pending', 'running', 'cancelling')",
        ) or 0
        if int(active) > 0:
            raise RuntimeError("Zaten devam eden bir liste temizliği var. Bitmesini veya iptal etmeyi bekle.")
        job_id = insert_returning_id(
            conn,
            """
            INSERT INTO mail_scrub_jobs
            (status, scope, tag_filter, contact_ids_json, total, processed,
             valid_count, invalid_count, unknown_count, catch_all_count,
             disposable_count, role_count, suppressed_count, skipped_count,
             error, last_contact_id, created_at, updated_at)
            VALUES ('pending', ?, ?, ?, 0, 0, 0, 0, 0, 0, 0, 0, 0, 0, '', 0, ?, ?)
            """,
            (scope or "filter", (tag_filter or "").strip(), ids_json, now, now),
        )
        conn.commit()
    # External worker varsa web thread'ine güvenme — worker reclaim eder.
    # Yoksa (veya local) burada başlat.
    if not _external_worker_mode():
        t = threading.Thread(target=_run_scrub_job, args=(job_id,), daemon=True, name=f"mail-scrub-{job_id}")
        t.start()
    else:
        # Yine de web'de dene (worker gecikirse); worker çift çalışmayı _SCRUB_RUNNING ile engelleyemez
        # (ayrı process) — bu yüzden external'da SADECE worker çalıştırır.
        pass
    return job_id


def job_public(row) -> dict:
    if not row:
        return {}
    d = dict(row) if not isinstance(row, dict) else dict(row)
    d.pop("contact_ids_json", None)
    return d
