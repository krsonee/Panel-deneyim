"""Makrobet davet / deneme test şablonu — unified engine preset’inden türetilir."""

from mail_template_engine_makrobet import preset_davet_test

DAVET_TEST_NAME = "Davet test"

_preset = preset_davet_test()
DAVET_TEST_SUBJECT = _preset["subject"]
DAVET_TEST_HTML = _preset["html_body"]
DAVET_TEST_TEXT = _preset["text_body"]


def ensure_davet_test_template(conn):
    from database import execute, fetchone, insert_returning_id, iso, utcnow

    now = iso(utcnow())
    existing = fetchone(conn, "SELECT id FROM mail_templates WHERE name = ?", (DAVET_TEST_NAME,))
    if existing:
        execute(
            conn,
            """
            UPDATE mail_templates
            SET subject = ?, html_body = ?, text_body = ?, updated_at = ?
            WHERE id = ?
            """,
            (DAVET_TEST_SUBJECT, DAVET_TEST_HTML, DAVET_TEST_TEXT, now, existing["id"]),
        )
        try:
            conn.commit()
        except Exception:
            pass
        return existing["id"]
    tid = insert_returning_id(
        conn,
        """
        INSERT INTO mail_templates (name, subject, html_body, text_body, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (DAVET_TEST_NAME, DAVET_TEST_SUBJECT, DAVET_TEST_HTML, DAVET_TEST_TEXT, now, now),
    )
    try:
        conn.commit()
    except Exception:
        pass
    return tid
