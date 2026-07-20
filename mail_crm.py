"""Gerçek CRM katmanı — yaşam döngüsü, skor, not, görev, zaman çizelgesi.

Mail Rehber (liste/import/etiket) ayrıdır; bu modül ilişki yönetimi içindir.
"""

from __future__ import annotations

import json
from contextlib import closing, suppress

from database import (
    execute,
    fetchall,
    fetchone,
    get_db,
    insert_returning_id,
    iso,
    scalar,
    uses_postgres,
    utcnow,
)

LIFECYCLES = (
    "lead",        # henüz ilişki yok / yeni
    "contacted",   # mail veya IVR ile temas
    "engaged",     # açtı / tıkladı
    "converted",   # üye / FTD sinyali
    "vip",         # özel takip
    "dormant",     # soğumuş
    "lost",        # unsub / bounce / vazgeçildi
)

LIFECYCLE_LABELS = {
    "lead": "Aday",
    "contacted": "Temas edildi",
    "engaged": "İlgili",
    "converted": "Dönüşen",
    "vip": "VIP",
    "dormant": "Uyuyan",
    "lost": "Kayıp",
}


def ensure_mail_crm_schema(conn):
    if uses_postgres():
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS mail_crm_notes (
                id SERIAL PRIMARY KEY,
                contact_id INTEGER NOT NULL,
                author TEXT NOT NULL DEFAULT '',
                body TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """,
        )
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS mail_crm_tasks (
                id SERIAL PRIMARY KEY,
                contact_id INTEGER NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                due_at TEXT,
                status TEXT NOT NULL DEFAULT 'open',
                author TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                done_at TEXT
            )
            """,
        )
    else:
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS mail_crm_notes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contact_id INTEGER NOT NULL,
                author TEXT NOT NULL DEFAULT '',
                body TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL
            )
            """,
        )
        execute(
            conn,
            """
            CREATE TABLE IF NOT EXISTS mail_crm_tasks (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                contact_id INTEGER NOT NULL,
                title TEXT NOT NULL DEFAULT '',
                due_at TEXT,
                status TEXT NOT NULL DEFAULT 'open',
                author TEXT NOT NULL DEFAULT '',
                created_at TEXT NOT NULL,
                done_at TEXT
            )
            """,
        )
    execute(conn, "CREATE INDEX IF NOT EXISTS idx_mail_crm_notes_contact ON mail_crm_notes(contact_id)")
    execute(conn, "CREATE INDEX IF NOT EXISTS idx_mail_crm_tasks_contact ON mail_crm_tasks(contact_id)")
    execute(conn, "CREATE INDEX IF NOT EXISTS idx_mail_crm_tasks_status ON mail_crm_tasks(status)")
    try:
        from database import _table_columns
        cols = _table_columns(conn, "mail_contacts") or set()
        if cols and "lifecycle" not in cols:
            execute(conn, "ALTER TABLE mail_contacts ADD COLUMN lifecycle TEXT NOT NULL DEFAULT 'lead'")
        if cols and "crm_score" not in cols:
            execute(conn, "ALTER TABLE mail_contacts ADD COLUMN crm_score INTEGER NOT NULL DEFAULT 0")
        if cols and "crm_owner" not in cols:
            execute(conn, "ALTER TABLE mail_contacts ADD COLUMN crm_owner TEXT NOT NULL DEFAULT ''")
        if cols and "last_touch_at" not in cols:
            execute(conn, "ALTER TABLE mail_contacts ADD COLUMN last_touch_at TEXT")
    except Exception:
        with suppress(Exception):
            conn.rollback()
    try:
        conn.commit()
    except Exception:
        pass


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


def compute_crm_score(conn, contact_id):
    """Etkileşim + etiket sinyallerinden 0–100 skor."""
    c = fetchone(conn, "SELECT * FROM mail_contacts WHERE id = ?", (contact_id,))
    if not c:
        return 0, "lead"
    tags = set(_parse_tags(c.get("tags")))
    score = 0
    sends = int(scalar(
        conn,
        "SELECT COUNT(*) FROM mail_sends WHERE contact_id = ? AND status IN ('sent','simulated')",
        (contact_id,),
    ) or 0)
    opens = int(scalar(
        conn,
        "SELECT COUNT(*) FROM mail_sends WHERE contact_id = ? AND opened_at IS NOT NULL",
        (contact_id,),
    ) or 0)
    clicks = int(scalar(
        conn,
        "SELECT COUNT(*) FROM mail_sends WHERE contact_id = ? AND clicked_at IS NOT NULL",
        (contact_id,),
    ) or 0)
    score += min(sends * 3, 15)
    score += min(opens * 10, 40)
    score += min(clicks * 12, 36)
    if "uye_oldu" in tags:
        score += 15
    if "ftd_yapti" in tags:
        score += 20
    if "mail_valid" in tags or "mail_mx_ok" in tags:
        score += 3
    if int(c.get("unsubscribed") or 0):
        score = max(score - 50, 0)

    # Otomatik lifecycle önerisi (manuel VIP/lost korunur)
    current = (c.get("lifecycle") or "lead").strip() or "lead"
    suggested = current
    if int(c.get("unsubscribed") or 0) or "mail_invalid" in tags:
        suggested = "lost"
    elif current == "vip":
        suggested = "vip"
    elif "ftd_yapti" in tags or "uye_oldu" in tags:
        suggested = "converted"
    elif opens > 0 or clicks > 0 or "mail_acan" in tags or "mail_tiklayan" in tags:
        suggested = "engaged"
    elif sends > 0:
        suggested = "contacted"
    else:
        suggested = "lead"

    # dormant: contacted/engaged ama uzun süredir dokunulmamış — last_touch yoksa skip
    last_touch = c.get("last_touch_at") or ""
    if suggested in ("contacted", "engaged") and last_touch:
        try:
            from datetime import datetime, timezone, timedelta
            raw = str(last_touch).replace("Z", "+00:00")
            if "T" not in raw and " " in raw:
                raw = raw.replace(" ", "T", 1)
            dt = datetime.fromisoformat(raw)
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            if datetime.now(timezone.utc) - dt > timedelta(days=45):
                suggested = "dormant"
        except Exception:
            pass

    # Manuel vip/lost'u skor güncellemesinde ezme
    if current in ("vip", "lost") and suggested != "lost":
        suggested = current
    if current == "lost" and int(c.get("unsubscribed") or 0):
        suggested = "lost"

    return min(int(score), 100), suggested


def refresh_contact_crm(conn, contact_id, *, apply_lifecycle=True):
    score, suggested = compute_crm_score(conn, contact_id)
    last_send = fetchone(
        conn,
        """
        SELECT COALESCE(opened_at, clicked_at, created_at) AS ts
        FROM mail_sends WHERE contact_id = ?
        ORDER BY id DESC LIMIT 1
        """,
        (contact_id,),
    )
    last_touch = (last_send or {}).get("ts") or None
    row = fetchone(conn, "SELECT lifecycle FROM mail_contacts WHERE id = ?", (contact_id,))
    lifecycle = (row or {}).get("lifecycle") or "lead"
    if apply_lifecycle and lifecycle not in ("vip",) and not (lifecycle == "lost" and suggested != "lost"):
        # vip elle korunur; lost sadece unsub ile veya elle
        if lifecycle != "lost" or suggested == "lost":
            lifecycle = suggested
    execute(
        conn,
        """
        UPDATE mail_contacts
        SET crm_score = ?, lifecycle = ?, last_touch_at = COALESCE(?, last_touch_at), updated_at = ?
        WHERE id = ?
        """,
        (score, lifecycle, last_touch, iso(utcnow()), contact_id),
    )
    return {"score": score, "lifecycle": lifecycle, "last_touch_at": last_touch}


def crm_overview(conn):
    ensure_mail_crm_schema(conn)
    by_life = {k: 0 for k in LIFECYCLES}
    rows = fetchall(
        conn,
        """
        SELECT COALESCE(NULLIF(TRIM(lifecycle), ''), 'lead') AS lifecycle, COUNT(*) AS n
        FROM mail_contacts
        GROUP BY 1
        """,
    ) or []
    for r in rows:
        key = (r["lifecycle"] or "lead").strip()
        if key not in by_life:
            by_life[key] = 0
        by_life[key] = int(r["n"] or 0)
    open_tasks = int(scalar(conn, "SELECT COUNT(*) FROM mail_crm_tasks WHERE status = 'open'") or 0)
    hot = int(scalar(conn, "SELECT COUNT(*) FROM mail_contacts WHERE crm_score >= 50") or 0)
    due_soon = int(scalar(
        conn,
        """
        SELECT COUNT(*) FROM mail_crm_tasks
        WHERE status = 'open' AND due_at IS NOT NULL AND due_at <= ?
        """,
        (iso(utcnow()),),
    ) or 0)
    notes = int(scalar(conn, "SELECT COUNT(*) FROM mail_crm_notes") or 0)
    return {
        "by_lifecycle": [
            {"key": k, "label": LIFECYCLE_LABELS.get(k, k), "count": by_life.get(k, 0)}
            for k in LIFECYCLES
        ],
        "open_tasks": open_tasks,
        "overdue_tasks": due_soon,
        "hot_contacts": hot,
        "notes_total": notes,
        "lifecycle_labels": LIFECYCLE_LABELS,
    }


def list_crm_pipeline(conn, lifecycle=None, q="", limit=80):
    ensure_mail_crm_schema(conn)
    limit = max(1, min(int(limit or 80), 200))
    clauses = []
    params = []
    lifecycle = (lifecycle or "").strip()
    if lifecycle:
        clauses.append("COALESCE(NULLIF(TRIM(lifecycle), ''), 'lead') = ?")
        params.append(lifecycle)
    q = (q or "").strip().lower()
    if q:
        clauses.append("(LOWER(email) LIKE ? OR LOWER(name) LIKE ? OR LOWER(COALESCE(crm_owner,'')) LIKE ?)")
        like = f"%{q}%"
        params.extend([like, like, like])
    where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
    rows = fetchall(
        conn,
        f"""
        SELECT id, email, name, tags, lifecycle, crm_score, crm_owner, last_touch_at,
               unsubscribed, source, updated_at
        FROM mail_contacts
        {where}
        ORDER BY crm_score DESC, id DESC
        LIMIT ?
        """,
        tuple(params) + (limit,),
    ) or []
    out = []
    for r in rows:
        d = dict(r)
        d["tags"] = _parse_tags(d.get("tags"))
        d["lifecycle"] = (d.get("lifecycle") or "lead").strip() or "lead"
        d["lifecycle_label"] = LIFECYCLE_LABELS.get(d["lifecycle"], d["lifecycle"])
        d["unsubscribed"] = bool(d.get("unsubscribed"))
        d["crm_score"] = int(d.get("crm_score") or 0)
        out.append(d)
    return out


def contact_timeline(conn, contact_id, limit=40):
    limit = max(1, min(int(limit or 40), 100))
    events = []
    sends = fetchall(
        conn,
        """
        SELECT id, channel, subject, status, created_at, opened_at, clicked_at, error
        FROM mail_sends WHERE contact_id = ?
        ORDER BY id DESC LIMIT ?
        """,
        (contact_id, limit),
    ) or []
    for s in sends:
        events.append({
            "type": "send",
            "at": s.get("created_at"),
            "title": f"Mail ({s.get('status')})",
            "detail": s.get("subject") or "",
            "meta": {"send_id": s.get("id"), "channel": s.get("channel"), "error": s.get("error") or ""},
        })
        if s.get("opened_at"):
            events.append({
                "type": "open",
                "at": s.get("opened_at"),
                "title": "Açıldı",
                "detail": s.get("subject") or "",
                "meta": {"send_id": s.get("id")},
            })
        if s.get("clicked_at"):
            events.append({
                "type": "click",
                "at": s.get("clicked_at"),
                "title": "Tıklandı",
                "detail": s.get("subject") or "",
                "meta": {"send_id": s.get("id")},
            })
    notes = fetchall(
        conn,
        "SELECT id, author, body, created_at FROM mail_crm_notes WHERE contact_id = ? ORDER BY id DESC LIMIT ?",
        (contact_id, limit),
    ) or []
    for n in notes:
        events.append({
            "type": "note",
            "at": n.get("created_at"),
            "title": "Not",
            "detail": (n.get("body") or "")[:300],
            "meta": {"note_id": n.get("id"), "author": n.get("author") or ""},
        })
    tasks = fetchall(
        conn,
        """
        SELECT id, title, due_at, status, author, created_at, done_at
        FROM mail_crm_tasks WHERE contact_id = ? ORDER BY id DESC LIMIT ?
        """,
        (contact_id, limit),
    ) or []
    for t in tasks:
        events.append({
            "type": "task",
            "at": t.get("created_at"),
            "title": f"Görev ({t.get('status')})",
            "detail": t.get("title") or "",
            "meta": {
                "task_id": t.get("id"),
                "due_at": t.get("due_at"),
                "status": t.get("status"),
                "author": t.get("author") or "",
            },
        })
    events.sort(key=lambda e: str(e.get("at") or ""), reverse=True)
    return events[:limit]


def get_contact_crm(conn, contact_id):
    ensure_mail_crm_schema(conn)
    row = fetchone(conn, "SELECT * FROM mail_contacts WHERE id = ?", (contact_id,))
    if not row:
        return None
    d = dict(row)
    d["tags"] = _parse_tags(d.get("tags"))
    d["lifecycle"] = (d.get("lifecycle") or "lead").strip() or "lead"
    d["lifecycle_label"] = LIFECYCLE_LABELS.get(d["lifecycle"], d["lifecycle"])
    d["unsubscribed"] = bool(d.get("unsubscribed"))
    d["crm_score"] = int(d.get("crm_score") or 0)
    d["timeline"] = contact_timeline(conn, contact_id)
    d["notes"] = [dict(n) for n in (fetchall(
        conn,
        "SELECT * FROM mail_crm_notes WHERE contact_id = ? ORDER BY id DESC LIMIT 50",
        (contact_id,),
    ) or [])]
    d["tasks"] = [dict(t) for t in (fetchall(
        conn,
        "SELECT * FROM mail_crm_tasks WHERE contact_id = ? ORDER BY CASE status WHEN 'open' THEN 0 ELSE 1 END, id DESC LIMIT 50",
        (contact_id,),
    ) or [])]
    stats = {
        "sends": int(scalar(conn, "SELECT COUNT(*) FROM mail_sends WHERE contact_id = ?", (contact_id,)) or 0),
        "opens": int(scalar(conn, "SELECT COUNT(*) FROM mail_sends WHERE contact_id = ? AND opened_at IS NOT NULL", (contact_id,)) or 0),
        "clicks": int(scalar(conn, "SELECT COUNT(*) FROM mail_sends WHERE contact_id = ? AND clicked_at IS NOT NULL", (contact_id,)) or 0),
    }
    d["engagement"] = stats
    return d


def add_note(conn, contact_id, body, author=""):
    body = (body or "").strip()
    if not body:
        raise ValueError("Not boş olamaz.")
    if not fetchone(conn, "SELECT id FROM mail_contacts WHERE id = ?", (contact_id,)):
        raise ValueError("Kontak bulunamadı.")
    now = iso(utcnow())
    nid = insert_returning_id(
        conn,
        "INSERT INTO mail_crm_notes (contact_id, author, body, created_at) VALUES (?, ?, ?, ?)",
        (contact_id, (author or "")[:120], body[:4000], now),
    )
    execute(
        conn,
        "UPDATE mail_contacts SET last_touch_at = ?, updated_at = ? WHERE id = ?",
        (now, now, contact_id),
    )
    return nid


def add_task(conn, contact_id, title, due_at=None, author=""):
    title = (title or "").strip()
    if not title:
        raise ValueError("Görev başlığı gerekli.")
    if not fetchone(conn, "SELECT id FROM mail_contacts WHERE id = ?", (contact_id,)):
        raise ValueError("Kontak bulunamadı.")
    now = iso(utcnow())
    tid = insert_returning_id(
        conn,
        """
        INSERT INTO mail_crm_tasks (contact_id, title, due_at, status, author, created_at, done_at)
        VALUES (?, ?, ?, 'open', ?, ?, NULL)
        """,
        (contact_id, title[:300], (due_at or "").strip() or None, (author or "")[:120], now),
    )
    return tid


def set_task_status(conn, task_id, status):
    status = (status or "").strip().lower()
    if status not in ("open", "done", "cancelled"):
        raise ValueError("Geçersiz görev durumu.")
    row = fetchone(conn, "SELECT id FROM mail_crm_tasks WHERE id = ?", (task_id,))
    if not row:
        raise ValueError("Görev bulunamadı.")
    now = iso(utcnow())
    execute(
        conn,
        "UPDATE mail_crm_tasks SET status = ?, done_at = ? WHERE id = ?",
        (status, now if status == "done" else None, task_id),
    )


def set_lifecycle(conn, contact_id, lifecycle, owner=None):
    lifecycle = (lifecycle or "").strip().lower()
    if lifecycle not in LIFECYCLES:
        raise ValueError("Geçersiz yaşam döngüsü.")
    if not fetchone(conn, "SELECT id FROM mail_contacts WHERE id = ?", (contact_id,)):
        raise ValueError("Kontak bulunamadı.")
    now = iso(utcnow())
    if owner is not None:
        execute(
            conn,
            "UPDATE mail_contacts SET lifecycle = ?, crm_owner = ?, updated_at = ?, last_touch_at = ? WHERE id = ?",
            (lifecycle, (owner or "")[:120], now, now, contact_id),
        )
    else:
        execute(
            conn,
            "UPDATE mail_contacts SET lifecycle = ?, updated_at = ?, last_touch_at = ? WHERE id = ?",
            (lifecycle, now, now, contact_id),
        )


def recompute_scores_batch(conn, limit=500):
    """Skoru düşük / eski kayıtlardan bir parti yeniler."""
    ensure_mail_crm_schema(conn)
    rows = fetchall(
        conn,
        "SELECT id FROM mail_contacts ORDER BY updated_at ASC NULLS LAST, id ASC LIMIT ?"
        if uses_postgres()
        else "SELECT id FROM mail_contacts ORDER BY updated_at ASC, id ASC LIMIT ?",
        (max(1, min(int(limit or 500), 2000)),),
    ) or []
    n = 0
    for r in rows:
        refresh_contact_crm(conn, int(r["id"]), apply_lifecycle=True)
        n += 1
    try:
        conn.commit()
    except Exception:
        pass
    return n
