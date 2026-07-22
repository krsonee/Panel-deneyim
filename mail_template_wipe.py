"""Tüm mail şablonlarını temizle — operatör sıfırdan kuracaksa."""

from __future__ import annotations

from database import execute, get_mail_setting, scalar, upsert_mail_setting

WIPE_FLAG = "mail_templates_cleared_custom_v1"
SKIP_AUTO_SEED = "mail_skip_auto_template_seed"


def auto_seed_disabled(conn) -> bool:
    return (get_mail_setting(conn, SKIP_AUTO_SEED, "") or "").strip() in ("1", "true", "yes", "on")


def wipe_all_mail_templates(conn) -> dict:
    """FK’leri temizleyip tüm şablonları siler; otomatik seed’i kapatır."""
    before = int(scalar(conn, "SELECT COUNT(*) FROM mail_templates") or 0)
    for sql in (
        "UPDATE mail_campaigns SET template_id = NULL WHERE template_id IS NOT NULL",
        "UPDATE mail_ivr_rules SET template_id = NULL WHERE template_id IS NOT NULL",
        "UPDATE mail_sends SET template_id = NULL WHERE template_id IS NOT NULL",
    ):
        try:
            execute(conn, sql)
        except Exception:
            try:
                conn.rollback()
            except Exception:
                pass
    try:
        execute(conn, "DELETE FROM mail_templates")
    except Exception as exc:
        try:
            conn.rollback()
        except Exception:
            pass
        raise RuntimeError(f"Şablonlar silinemedi: {exc}") from exc
    upsert_mail_setting(conn, WIPE_FLAG, "1")
    upsert_mail_setting(conn, SKIP_AUTO_SEED, "1")
    try:
        conn.commit()
    except Exception:
        pass
    after = int(scalar(conn, "SELECT COUNT(*) FROM mail_templates") or 0)
    return {"deleted": max(0, before - after), "remaining": after}


def ensure_templates_wiped_once(conn) -> dict | None:
    """Deploy sonrası bir kez tüm şablonları temizle."""
    if (get_mail_setting(conn, WIPE_FLAG, "") or "").strip() == "1":
        return None
    return wipe_all_mail_templates(conn)
