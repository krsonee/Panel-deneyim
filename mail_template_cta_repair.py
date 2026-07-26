"""Şablon CTA temizliği — marka karışması yok.

Bizzo şablonları → yalnızca https://girbize.com
Makro şablonları → yalnızca https://makrovip.com/Vipmail

Click-link tablosuna dokunulmaz; gönderimde butonlar zaten direkt siteye gider.
"""

from __future__ import annotations

from database import execute, fetchall, upsert_mail_setting

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
        # Bizzo’dan Makro CTA / Vipmail temizle
        (MAKRO_TOKEN, BIZZO_TOKEN),
        ("{{link:sc:https://makrovip.com/Vipmail}}", BIZZO_TOKEN),
        ("{{link:https://makrovip.com/Vipmail}}", BIZZO_TOKEN),
        ("{{link:sc:https://makrogir.com}}", BIZZO_TOKEN),
        ("{{link:sc:https://vipmakro.com}}", BIZZO_TOKEN),
        (MAKRO_CTA, BIZZO_CTA),
        ("https://makrovip.com/Vipmail", BIZZO_CTA),
        ("https://makrovip.com/vipmail", BIZZO_CTA),
        ("https://www.makrovip.com/Vipmail", BIZZO_CTA),
        ("https://makrogir.com/", BIZZO_CTA),
        ("https://makrogir.com", BIZZO_CTA),
        ("https://vipmakro.com/", BIZZO_CTA),
        ("https://vipmakro.com", BIZZO_CTA),
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
        # Makro’dan Bizzo CTA temizle
        ("{{link:sc:https://girbize.com/}}", MAKRO_TOKEN),
        ("{{link:sc:https://girbize.com}}", MAKRO_TOKEN),
        ("{{link:https://girbize.com}}", MAKRO_TOKEN),
        ("{{link:sc:https://bizzocasino168.com}}", MAKRO_TOKEN),
        ("{{link:sc:https://www.bizzocasino168.com}}", MAKRO_TOKEN),
        (BIZZO_TOKEN, MAKRO_TOKEN),
        ("https://girbize.com/", MAKRO_CTA),
        ("https://girbize.com", MAKRO_CTA),
        ("http://girbize.com/", MAKRO_CTA),
        ("http://girbize.com", MAKRO_CTA),
        ("https://www.bizzocasino168.com/", MAKRO_CTA),
        ("https://www.bizzocasino168.com", MAKRO_CTA),
        ("https://bizzocasino168.com/", MAKRO_CTA),
        ("https://bizzocasino168.com", MAKRO_CTA),
    ):
        out = out.replace(old, new)
    return out


def repair_mail_cta_links(conn) -> dict:
    """Şablon gövdelerini markaya göre düzelt (her deploy’da)."""
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

    upsert_mail_setting(conn, "mail_cta_repair_v20260726c", "1")
    try:
        conn.commit()
    except Exception:
        pass
    return {
        "templates_updated": tpl_updated,
        "bizzo_cta": BIZZO_CTA,
        "makro_cta": MAKRO_CTA,
    }
