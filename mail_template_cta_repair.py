"""Şablon + gönderilmiş takip linklerinde CTA URL düzeltmesi.

Bizzo → https://girbize.com
Makro → https://makrovip.com/Vipmail

Gönderilmiş maillerdeki /m/c/<token> butonları dest_url üzerinden yönlenir;
şablon güncellemek yetmez — mail_click_links.dest_url da düzeltilir.
"""

from __future__ import annotations

from database import execute, fetchall, scalar, upsert_mail_setting

BIZZO_CTA = "https://girbize.com"
MAKRO_CTA = "https://makrovip.com/Vipmail"
BIZZO_TOKEN = "{{link:sc:https://girbize.com}}"
MAKRO_TOKEN = "{{link:sc:https://makrovip.com/Vipmail}}"


def _is_bizzo_template_name(name: str) -> bool:
    n = (name or "").strip().lower()
    return n.startswith("bizzo") or " bizzo" in n


def _rewrite_bizzo_body(body: str) -> str:
    out = body or ""
    for old, new in (
        ("{{link:sc:https://girbize.com/}}", BIZZO_TOKEN),
        ("{{link:sc:https://girbize.com}}", BIZZO_TOKEN),
        ("{{link:https://girbize.com/}}", BIZZO_TOKEN),
        ("{{link:https://girbize.com}}", BIZZO_TOKEN),
        ("{{link:sc:https://www.bizzocasino168.com/}}", BIZZO_TOKEN),
        ("{{link:sc:https://www.bizzocasino168.com}}", BIZZO_TOKEN),
        ("{{link:sc:https://bizzocasino168.com/}}", BIZZO_TOKEN),
        ("{{link:sc:https://bizzocasino168.com}}", BIZZO_TOKEN),
        ("https://girbize.com/", BIZZO_CTA),
        ("http://girbize.com/", BIZZO_CTA),
        ("http://girbize.com", BIZZO_CTA),
        ("https://www.bizzocasino168.com/", BIZZO_CTA),
        ("https://www.bizzocasino168.com", BIZZO_CTA),
        ("http://www.bizzocasino168.com/", BIZZO_CTA),
        ("http://www.bizzocasino168.com", BIZZO_CTA),
        ("https://bizzocasino168.com/", BIZZO_CTA),
        ("https://bizzocasino168.com", BIZZO_CTA),
        (MAKRO_TOKEN, BIZZO_TOKEN),
        (MAKRO_CTA, BIZZO_CTA),
    ):
        out = out.replace(old, new)
    return out


def _rewrite_makro_body(body: str) -> str:
    out = body or ""
    for old, new in (
        ("{{link:sc:https://makrovip.com/vipmail}}", MAKRO_TOKEN),
        ("{{link:sc:https://makrovip.com/VipMail}}", MAKRO_TOKEN),
        ("{{link:https://makrovip.com/Vipmail}}", MAKRO_TOKEN),
        ("{{link:sc:https://www.makrovip.com/Vipmail}}", MAKRO_TOKEN),
        ("{{link:sc:https://makrogir.com/}}", MAKRO_TOKEN),
        ("{{link:sc:https://makrogir.com}}", MAKRO_TOKEN),
        ("{{link:sc:https://vipmakro.com/}}", MAKRO_TOKEN),
        ("{{link:sc:https://vipmakro.com}}", MAKRO_TOKEN),
        ("http://makrovip.com/Vipmail", MAKRO_CTA),
        ("https://www.makrovip.com/Vipmail", MAKRO_CTA),
        ("https://makrogir.com/", MAKRO_CTA),
        ("https://makrogir.com", MAKRO_CTA),
        ("https://vipmakro.com/", MAKRO_CTA),
        ("https://vipmakro.com", MAKRO_CTA),
        ("{{link:sc:https://girbize.com/}}", MAKRO_TOKEN),
        ("{{link:sc:https://girbize.com}}", MAKRO_TOKEN),
        ("https://girbize.com/", MAKRO_CTA),
        ("https://girbize.com", MAKRO_CTA),
    ):
        out = out.replace(old, new)
    return out


def repair_mail_cta_links(conn) -> dict:
    """Şablon gövdeleri + mail_click_links.dest_url düzelt (her deploy’da güvenli)."""
    templates = fetchall(conn, "SELECT id, name, html_body, text_body FROM mail_templates") or []
    tpl_updated = 0
    for row in templates:
        name = row["name"] or ""
        html = row["html_body"] or ""
        text = row["text_body"] or ""
        if _is_bizzo_template_name(name):
            new_html = _rewrite_bizzo_body(html)
            new_text = _rewrite_bizzo_body(text)
        else:
            new_html = _rewrite_makro_body(html)
            new_text = _rewrite_makro_body(text)
        if new_html != html or new_text != text:
            execute(
                conn,
                "UPDATE mail_templates SET html_body = ?, text_body = ? WHERE id = ?",
                (new_html, new_text, row["id"]),
            )
            tpl_updated += 1

    try:
        bizzo_before = int(scalar(
            conn,
            """
            SELECT COUNT(*) FROM mail_click_links
            WHERE dest_url IS NOT NULL AND dest_url != ?
              AND (
                LOWER(dest_url) LIKE 'https://girbize.com%'
                OR LOWER(dest_url) LIKE 'http://girbize.com%'
                OR LOWER(dest_url) LIKE '%bizzocasino%'
              )
            """,
            (BIZZO_CTA,),
        ) or 0)
    except Exception:
        bizzo_before = 0

    execute(
        conn,
        """
        UPDATE mail_click_links
        SET dest_url = ?
        WHERE dest_url IS NOT NULL
          AND dest_url != ?
          AND (
            LOWER(dest_url) LIKE 'https://girbize.com%'
            OR LOWER(dest_url) LIKE 'http://girbize.com%'
            OR LOWER(dest_url) LIKE '%bizzocasino%'
          )
        """,
        (BIZZO_CTA, BIZZO_CTA),
    )

    try:
        makro_before = int(scalar(
            conn,
            """
            SELECT COUNT(*) FROM mail_click_links
            WHERE dest_url IS NOT NULL AND dest_url != ?
              AND (
                LOWER(dest_url) LIKE '%makrovip.com%'
                OR LOWER(dest_url) LIKE '%makroaffi%'
                OR LOWER(dest_url) LIKE '%makrogir.com%'
                OR LOWER(dest_url) LIKE '%vipmakro.com%'
              )
            """,
            (MAKRO_CTA,),
        ) or 0)
    except Exception:
        makro_before = 0

    execute(
        conn,
        """
        UPDATE mail_click_links
        SET dest_url = ?
        WHERE dest_url IS NOT NULL
          AND dest_url != ?
          AND (
            LOWER(dest_url) LIKE '%makrovip.com%'
            OR LOWER(dest_url) LIKE '%makroaffi%'
            OR LOWER(dest_url) LIKE '%makrogir.com%'
            OR LOWER(dest_url) LIKE '%vipmakro.com%'
          )
        """,
        (MAKRO_CTA, MAKRO_CTA),
    )

    upsert_mail_setting(conn, "mail_cta_repair_v20260726b", "1")
    try:
        conn.commit()
    except Exception:
        pass
    return {
        "templates_updated": tpl_updated,
        "click_links_bizzo": bizzo_before,
        "click_links_makro": makro_before,
        "bizzo_cta": BIZZO_CTA,
        "makro_cta": MAKRO_CTA,
    }
