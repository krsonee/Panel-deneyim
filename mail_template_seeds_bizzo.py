"""Bizzo Casino mailing şablonları — promotions sayfasından yatırım odaklı 6 preset.

Kaynak: https://www.bizzocasino168.com/promotions
Engine: mail_template_engine_bizzo.py
Logo: __BIZZO_LOGO__ → /static/mailing/bizzo-logo.png
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
from mail_template_engine_bizzo import build_all_presets

SEED_FLAG = "seeded_bizzo_templates_v2026a"

TEMPLATES = build_all_presets()


def seed_bizzo_mail_templates(
    conn,
    force_missing=False,
    overwrite=False,
    allow_when_skipped=False,
):
    """Seed Bizzo templates. Startup’ta overwrite=True + allow_when_skipped=True kullan."""
    _ = force_missing
    if not allow_when_skipped:
        try:
            from mail_template_wipe import auto_seed_disabled
            if auto_seed_disabled(conn):
                return {"added": 0, "updated": 0, "skipped": True}
        except Exception:
            pass

    now = iso(utcnow())
    added = 0
    updated = 0
    for item in TEMPLATES:
        name = item["name"]
        exists = fetchone(conn, "SELECT id FROM mail_templates WHERE name = ?", (name,))
        if exists:
            if overwrite and (item.get("html_body") or "").strip():
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

    # Eski tekil lansman şablonunu yeni ilk-yatırım içeriğiyle senkron tut (varsa)
    legacy = fetchone(
        conn, "SELECT id FROM mail_templates WHERE name = ?", ("Bizzo · TR Lansman / Hoş Geldin",)
    )
    if legacy and overwrite:
        fresh = next((t for t in TEMPLATES if "İlk Yatırım" in t["name"]), None)
        if fresh:
            execute(
                conn,
                """
                UPDATE mail_templates
                SET subject = ?, html_body = ?, text_body = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    fresh["subject"],
                    fresh.get("html_body") or "",
                    fresh.get("text_body") or "",
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
