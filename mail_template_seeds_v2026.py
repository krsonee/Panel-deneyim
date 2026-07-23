"""Makrobet 2026 mailing şablonları — unified template engine (6 preset).

Engine: mail_template_engine_makrobet.py
Logo: __MAIL_LOGO__ → makrobet-logo-mail.jpg
CTA: {{link:sc:https://makrovip.com/Vipmail}} (buton içinde; ham URL yok)
"""

from __future__ import annotations

from database import (
    execute,
    fetchone,
    insert_returning_id,
    iso,
    upsert_mail_setting,
    utcnow,
)
from mail_template_engine_makrobet import build_all_presets

SEED_FLAG = "seeded_makrobet_templates_v2026e"

TEMPLATES = build_all_presets()


def seed_makrobet_2026_templates(conn, overwrite=True):
    now = iso(utcnow())
    added = 0
    updated = 0
    for item in TEMPLATES:
        name = item["name"]
        exists = fetchone(conn, "SELECT id FROM mail_templates WHERE name = ?", (name,))
        if exists:
            if overwrite:
                execute(
                    conn,
                    """
                    UPDATE mail_templates
                    SET subject = ?, html_body = ?, text_body = ?, updated_at = ?
                    WHERE id = ?
                    """,
                    (
                        item["subject"],
                        item.get("html_body") or "",
                        item.get("text_body") or "",
                        now,
                        exists["id"],
                    ),
                )
                updated += 1
            continue
        insert_returning_id(
            conn,
            """
            INSERT INTO mail_templates (name, subject, html_body, text_body, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                name,
                item["subject"],
                item.get("html_body") or "",
                item.get("text_body") or "",
                now,
                now,
            ),
        )
        added += 1

    # Legacy "Davet test" adını yeni preset ile senkron tut
    davet = next((t for t in TEMPLATES if t["name"] == "2026 · Davet Test"), None)
    if davet:
        legacy = fetchone(conn, "SELECT id FROM mail_templates WHERE name = ?", ("Davet test",))
        if legacy and overwrite:
            execute(
                conn,
                """
                UPDATE mail_templates
                SET subject = ?, html_body = ?, text_body = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    davet["subject"],
                    davet.get("html_body") or "",
                    davet.get("text_body") or "",
                    now,
                    legacy["id"],
                ),
            )
            updated += 1

    upsert_mail_setting(conn, SEED_FLAG, "1")
    try:
        conn.commit()
    except Exception:
        pass
    return {"added": added, "updated": updated}
