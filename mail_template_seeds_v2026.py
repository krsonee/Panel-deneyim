"""Makrobet 2026 mailing şablonları — unified template engine presets.

Engine: mail_template_engine_makrobet.py
Logo: __MAIL_LOGO__ → makrobet-logo-mail.png
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
from mail_template_engine_makrobet import build_all_presets, preset_davet_deneme_kayip

SEED_FLAG = "seeded_makrobet_templates_v2026m"

TEMPLATES = build_all_presets()

DAVET_DENEME_KAYIP_NAME = "2026 · Davet · Deneme + %100 Kayıp"


def _upsert_template(conn, item: dict, *, overwrite: bool) -> str:
    """Returns 'added' | 'updated' | 'kept'."""
    now = iso(utcnow())
    name = item["name"]
    exists = fetchone(conn, "SELECT id FROM mail_templates WHERE name = ?", (name,))
    if exists:
        if not overwrite:
            return "kept"
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
        return "updated"
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
    return "added"


def seed_davet_deneme_kayip_template(conn, overwrite=True):
    """Tek davet şablonu — wipe skip açıkken de eklenebilir."""
    action = _upsert_template(conn, preset_davet_deneme_kayip(), overwrite=overwrite)
    try:
        conn.commit()
    except Exception:
        pass
    return {
        "ok": True,
        "name": DAVET_DENEME_KAYIP_NAME,
        "added": 1 if action == "added" else 0,
        "updated": 1 if action == "updated" else 0,
        "action": action,
    }


def seed_makrobet_2026_templates(conn, overwrite=True, allow_when_skipped=False):
    if not allow_when_skipped:
        try:
            from mail_template_wipe import auto_seed_disabled
            if auto_seed_disabled(conn):
                return {"added": 0, "updated": 0, "skipped": True}
        except Exception:
            pass
    added = 0
    updated = 0
    for item in TEMPLATES:
        action = _upsert_template(conn, item, overwrite=overwrite)
        if action == "added":
            added += 1
        elif action == "updated":
            updated += 1

    # Legacy "Davet test" adını yeni preset ile senkron tut
    davet = next((t for t in TEMPLATES if t["name"] == "2026 · Davet Test"), None)
    if davet:
        legacy = fetchone(conn, "SELECT id FROM mail_templates WHERE name = ?", ("Davet test",))
        if legacy and overwrite:
            now = iso(utcnow())
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
