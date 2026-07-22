"""Bizzo Casino mailing şablonu — site markası + TR promo içeriği.

Görsel: https://www.bizzocasino168.com
Logo: /static/mailing/bizzo-logo.png (__BIZZO_LOGO__)
Palet: bg #2b1234 · yeşil #2ecc71 · turuncu CTA #ff9f1a · metin #ffffff
"""

from __future__ import annotations

from database import (
    execute,
    fetchone,
    get_mail_setting,
    insert_returning_id,
    iso,
    upsert_mail_setting,
    utcnow,
)

SEED_FLAG = "seeded_bizzo_templates_v2"

SITE_URL = "https://www.bizzocasino168.com"
CTA = "{{link:sc:https://www.bizzocasino168.com}}"

_BG = "#2b1234"
_CARD = "#1a0f24"
_ROW = "#3a1f4a"
_GREEN = "#2ecc71"
_ORANGE = "#ff9f1a"
_TEXT = "#ffffff"
_MUTED = "#c4b0d4"
_BORDER = "#5a3a6e"
_LOGO = "__BIZZO_LOGO__"


def _bizzo_html():
    """Tek ana hoş geldin / TR lansman şablonu — table + inline CSS."""
    offer_rows = [
        ("500 TL", "Deneme Bonusu", "Hemen dene — kayıt hediyesi"),
        ("%100", "50.000 TL’ye kadar", "Çevrimsiz Slot Hoş Geldin<br><span style=\"color:#2ecc71;font-size:12px;\">Çekim yapana kadar sınırsız</span>"),
        ("%100", "Pragmatic Play", "Çevrimsiz Pragmatic Play Bonusu"),
        ("%50", "Kayıp Bonusu", "%25 anlık + %25 ertesi gün<br><span style=\"color:#c4b0d4;font-size:12px;\">Toplamda %50 kayıp bonusu</span>"),
        ("5.000.000 TL", "Günlük Çekim", "Günlük 5.000.000 TL’ye kadar çekim imkânı"),
    ]
    rows_html = []
    for big, title, sub in offer_rows:
        rows_html.append(f"""
          <tr>
            <td style="padding:0 22px 12px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{_ROW};border:1px solid {_BORDER};border-radius:14px;">
                <tr>
                  <td width="112" valign="middle" align="center" style="padding:16px 10px;font-family:Arial,Helvetica,sans-serif;">
                    <div style="font-size:20px;font-weight:800;color:{_GREEN};line-height:1.15;">{big}</div>
                  </td>
                  <td valign="middle" style="padding:16px 16px 16px 0;font-family:Arial,Helvetica,sans-serif;border-left:1px solid {_BORDER};">
                    <div style="font-size:15px;font-weight:800;color:{_TEXT};padding-left:14px;">{title}</div>
                    <div style="font-size:13px;line-height:1.45;color:{_MUTED};padding:4px 0 0 14px;">{sub}</div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>""")
    offers = "\n".join(rows_html)

    return f"""<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width,initial-scale=1">
  <title>Bizzo Casino — Türkiye’de</title>
</head>
<body style="margin:0;padding:0;background:{_BG};">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{_BG};">
    <tr>
      <td align="center" style="padding:24px 12px;">
        <table role="presentation" width="600" cellpadding="0" cellspacing="0" style="max-width:600px;width:100%;background:{_CARD};border-radius:18px;overflow:hidden;border:1px solid {_BORDER};">

          <!-- Header / logo -->
          <tr>
            <td align="center" style="padding:28px 24px 12px;background:linear-gradient(180deg,#3a1a4a 0%,{_CARD} 100%);">
              <a href="{CTA}" style="text-decoration:none;">
                <img src="{_LOGO}" alt="Bizzo Casino" width="220" height="92" style="display:block;width:220px;max-width:72%;height:auto;border:0;margin:0 auto;">
              </a>
            </td>
          </tr>

          <!-- Hero -->
          <tr>
            <td align="center" style="padding:8px 28px 6px;font-family:Arial,Helvetica,sans-serif;">
              <span style="display:inline-block;background:{_GREEN};color:{_BG};font-size:11px;font-weight:800;letter-spacing:0.08em;text-transform:uppercase;padding:6px 14px;border-radius:999px;">Yeni</span>
            </td>
          </tr>
          <tr>
            <td align="center" style="padding:10px 28px 6px;font-family:Arial,Helvetica,sans-serif;font-size:28px;font-weight:800;line-height:1.25;color:{_TEXT};">
              Bizzo Artık Türkiye’de
            </td>
          </tr>
          <tr>
            <td align="center" style="padding:0 36px 20px;font-family:Arial,Helvetica,sans-serif;font-size:15px;line-height:1.5;color:{_MUTED};">
              Merhaba {{{{name}}}}, büyük karşılama paketimiz hazır.
              Deneme bonusundan çevrimsiz slot hoş geldine, kayıp bonusundan yüksek çekim limitine kadar her şey seni bekliyor.
            </td>
          </tr>

          <!-- Primary CTA -->
          <tr>
            <td align="center" style="padding:0 28px 22px;">
              <a href="{CTA}" style="display:inline-block;background:{_ORANGE};color:#1a0a10;font-family:Arial,Helvetica,sans-serif;font-size:16px;font-weight:800;text-decoration:none;padding:16px 36px;border-radius:12px;box-shadow:0 6px 0 #c46f00;">
                Hemen Katıl — Bonusu Al
              </a>
            </td>
          </tr>

          <!-- Offers -->
          <tr>
            <td style="padding:4px 28px 10px;font-family:Arial,Helvetica,sans-serif;font-size:13px;font-weight:800;letter-spacing:0.06em;text-transform:uppercase;color:{_GREEN};">
              Karşılama paketi
            </td>
          </tr>
{offers}

          <!-- Mid CTA -->
          <tr>
            <td align="center" style="padding:8px 28px 8px;">
              <a href="{CTA}" style="display:inline-block;background:{_GREEN};color:{_BG};font-family:Arial,Helvetica,sans-serif;font-size:15px;font-weight:800;text-decoration:none;padding:14px 32px;border-radius:12px;">
                Siteye Git — bizzocasino168.com
              </a>
            </td>
          </tr>

          <!-- Highlight strip -->
          <tr>
            <td style="padding:18px 22px 8px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:linear-gradient(90deg,{_GREEN}22,{_ORANGE}22);border:1px solid {_GREEN};border-radius:14px;">
                <tr>
                  <td align="center" style="padding:18px 16px;font-family:Arial,Helvetica,sans-serif;">
                    <div style="font-size:12px;font-weight:700;color:{_GREEN};letter-spacing:0.08em;text-transform:uppercase;">Öne çıkan</div>
                    <div style="font-size:18px;font-weight:800;color:{_TEXT};padding-top:6px;">%100 Çevrimsiz Slot Hoş Geldin</div>
                    <div style="font-size:13px;color:{_MUTED};padding-top:4px;">50.000 TL’ye kadar · Çekim yapana kadar sınırsız</div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Final CTA -->
          <tr>
            <td align="center" style="padding:20px 28px 28px;">
              <a href="{CTA}" style="display:inline-block;background:{_ORANGE};color:#1a0a10;font-family:Arial,Helvetica,sans-serif;font-size:16px;font-weight:800;text-decoration:none;padding:16px 36px;border-radius:12px;">
                Bonusu Kap — Şimdi Oyna
              </a>
              <div style="padding-top:14px;font-family:Arial,Helvetica,sans-serif;font-size:12px;">
                <a href="{CTA}" style="color:{_GREEN};text-decoration:underline;">www.bizzocasino168.com</a>
              </div>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding:16px 28px 24px;border-top:1px solid {_BORDER};font-family:Arial,Helvetica,sans-serif;font-size:11px;line-height:1.5;color:{_MUTED};text-align:center;">
              18+ · Sorumlu oyun. Oyun bağımlılığa yol açabilir.<br>
              Bu e-posta Bizzo Casino bilgilendirmesidir.
              İstemezsen <span style="color:{_TEXT};">abonelikten çık</span> linkini kullan.
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


def _bizzo_text():
    return f"""Merhaba {{{{name}}}},

Bizzo Artık Türkiye'de!

• 500 TL Deneme Bonusu
• %100 / 50.000 TL'ye kadar Çevrimsiz Slot Hoş Geldin (çekim yapana kadar sınırsız)
• %100 Çevrimsiz Pragmatic Play Bonusu
• %25 Anlık + %25 Ertesi gün = %50 Kayıp Bonusu
• Günlük 5.000.000 TL'ye kadar çekim

Hemen katıl: {SITE_URL}

18+ · Sorumlu oyun
Bizzo Casino
"""


HTML_TEMPLATES = [
    {
        "name": "Bizzo · TR Lansman / Hoş Geldin",
        "subject": "{{name}}, Bizzo artık Türkiye'de — 500 TL deneme + çevrimsiz hoş geldin",
        "html_body": _bizzo_html(),
        "text_body": _bizzo_text(),
    },
]


def seed_bizzo_mail_templates(conn, force_missing=False, overwrite=False, allow_when_skipped=False):
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
    _ = force_missing
    already = (get_mail_setting(conn, SEED_FLAG, "") or "").strip() == "1"
    if not already:
        overwrite = True
    for item in HTML_TEMPLATES:
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
    upsert_mail_setting(conn, SEED_FLAG, "1")
    try:
        conn.commit()
    except Exception:
        pass
    return {"added": added, "updated": updated}
