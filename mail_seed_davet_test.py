"""Makrobet davet mail şablonu — deploy'da otomatik seed edilir.

Canlı site (makrobet804.com/tr/pages/promotions):
  - Arka plan: #061c3d
  - Kart: #0a2244
  - Metin: #e6f0fe
  - CTA: #ffd53e / metin #0f1328
  - Logo (küçük): logo-black.png 330×64
  - Promo görselleri: gateway.makroz.org/cdn/makrobet/...
"""

DAVET_TEST_NAME = "Davet test"

DAVET_TEST_SUBJECT = "{{name}}, Makrobet'te seni 3.000 TL deneme kasası bekliyor!"

# logo.png 6114px genişlikte — mailde patlıyor; site header'daki kompakt logo kullanılıyor.
LOGO_URL = "https://makrobet804.com/cdn/makrobet/upload_files/logo-black.png"
PROMO_LINK = "{{link:sc:https://makrobet804.com/tr/pages/promotions}}"

# Site renkleri
C_BG = "#061c3d"
C_CARD = "#0a2244"
C_CARD_INNER = "#0d2a52"
C_TEXT = "#e6f0fe"
C_MUTED = "#9aabd4"
C_GOLD = "#ffd53e"
C_DARK = "#0f1328"

PROMOS = [
    {
        "title": "%100 Kayıp Bonusu",
        "desc": "Sıfır riskle yatırım senden, güvence Makrobet'ten.",
        "img": "https://gateway.makroz.org/cdn/makrobet/uploads/general/100KaypWeb-b93d6f94-ba47-49d3-bfee-2f59a54f3402.png",
    },
    {
        "title": "Arkadaşını Getir",
        "desc": "Arkadaşının aldığı yatırım bonusunu sana da ekleyelim.",
        "img": "https://gateway.makroz.org/cdn/makrobet/uploads/general/ArkadasWeb-4419cecd-2bcc-4030-918e-07c39b2a6090.png",
    },
    {
        "title": "Makro Görev",
        "desc": "Günlük görevlerini tamamla, Görev Kasa ödülünü kaçırma.",
        "img": "https://gateway.makroz.org/cdn/makrobet/promotion-posts/41/cover_mobile.png",
    },
    {
        "title": "Happy Hours",
        "desc": "Her yatırıma ek sürpriz — Mutlu Saatler aktif.",
        "img": "https://gateway.makroz.org/cdn/makrobet/uploads/general/YatEkCase-7646aa0d-c9de-4e4f-a28b-27ae4ee8a2e4.png",
    },
    {
        "title": "Amusnet Yarışı",
        "desc": "500.000₺ ödüllü yarış — zirvedeki yerini ayırt.",
        "img": "https://gateway.makroz.org/cdn/makrobet/uploads/general/Race-e1e97157-150a-4c10-84f9-b1feb9cd4824.png",
    },
    {
        "title": "Kripto Ultra Kasa",
        "desc": "Kripto yatır, havale çek — 10.000₺ Ultra Kasa kazan.",
        "img": "https://gateway.makroz.org/cdn/makrobet/uploads/general/K&HWeb-970f7a17-d9d0-48f0-a61f-459610227bd3.png",
    },
]


def _promo_cell(p):
    return f"""<td class="promo-col" width="50%" valign="top" style="padding:5px;">
<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color:{C_CARD_INNER};border-radius:10px;border:1px solid rgba(255,213,62,0.14);overflow:hidden;">
  <tr>
    <td style="padding:0;line-height:0;background-color:#05101f;">
      <a href="{PROMO_LINK}" style="text-decoration:none;">
        <img src="{p['img']}" alt="{p['title']}" width="268" height="76" class="promo-thumb" style="display:block;width:268px;max-width:100%;height:76px;border:0;margin:0;">
      </a>
    </td>
  </tr>
  <tr>
    <td style="padding:10px 11px 12px;">
      <div style="font-size:10px;font-weight:800;color:{C_GOLD};text-transform:uppercase;letter-spacing:0.25px;line-height:1.3;">{p['title']}</div>
      <div style="font-size:11px;color:{C_MUTED};margin-top:4px;line-height:1.45;">{p['desc']}</div>
    </td>
  </tr>
</table>
</td>"""


def _promo_grid_html():
    rows = []
    for i in range(0, len(PROMOS), 2):
        pair = PROMOS[i : i + 2]
        cells = [_promo_cell(p) for p in pair]
        if len(cells) == 1:
            cells.append('<td width="50%" style="padding:5px;"></td>')
        rows.append(
            '<table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="margin-bottom:4px;"><tr>'
            + "".join(cells)
            + "</tr></table>"
        )
    return "\n".join(rows)


DAVET_TEST_TEXT = f"""Merhaba {{{{name}}}},

Makrobet ailesine özel davetlisin!

★ YENİ ÜYELERE ÖZEL: 3.000 TL DENEME KASASI ★
Kayıt ol, deneme kasanı al ve hemen oynamaya başla.

Güncel promosyonlar:
{chr(10).join('- ' + p['title'] + ' — ' + p['desc'] for p in PROMOS)}

Tüm promosyonları gör: {PROMO_LINK}

18 yaşından büyükler içindir. Sorumlu oyun.
"""

DAVET_TEST_HTML = f"""<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>Makrobet Davet</title>
  <style type="text/css">
    body {{ margin:0; padding:0; }}
    img {{ border:0; outline:none; text-decoration:none; -ms-interpolation-mode:bicubic; }}
    .promo-thumb {{ object-fit:cover; }}
    @media only screen and (max-width:620px) {{
      .stack {{ display:block !important; width:100% !important; }}
      .promo-col {{ display:block !important; width:100% !important; padding:5px 0 !important; }}
    }}
  </style>
</head>
<body style="margin:0;padding:0;background-color:{C_BG};font-family:Arial,Helvetica,sans-serif;-webkit-text-size-adjust:100%;">
  <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background-color:{C_BG};">
    <tr>
      <td align="center" style="padding:24px 10px;">
        <table role="presentation" class="stack" width="600" cellspacing="0" cellpadding="0" border="0" style="max-width:600px;width:100%;border-collapse:separate;">
          <!-- Header -->
          <tr>
            <td style="background-color:{C_CARD};padding:18px 24px 14px;text-align:center;border-radius:14px 14px 0 0;border:1px solid rgba(255,213,62,0.18);border-bottom:none;">
              <a href="{PROMO_LINK}" style="text-decoration:none;">
                <img src="{LOGO_URL}" alt="Makrobet" width="168" height="33" style="display:inline-block;width:168px;max-width:168px;height:33px;border:0;">
              </a>
            </td>
          </tr>
          <!-- Greeting -->
          <tr>
            <td style="background-color:{C_CARD};border-left:1px solid rgba(255,213,62,0.12);border-right:1px solid rgba(255,213,62,0.12);padding:18px 24px 10px;">
              <p style="margin:0 0 6px;font-size:10px;color:{C_GOLD};font-weight:700;text-transform:uppercase;letter-spacing:1.4px;">Özel davet</p>
              <h1 style="margin:0 0 8px;font-size:20px;line-height:1.35;color:{C_TEXT};font-weight:700;">Merhaba {{{{name}}}}, sana özel fırsatlar hazır</h1>
              <p style="margin:0;font-size:13px;line-height:1.6;color:{C_MUTED};">Makrobet'te yüksek oranlar, hızlı ödeme ve güncel promosyonlarla kazanmaya bir adım uzaktasın.</p>
            </td>
          </tr>
          <!-- 3.000 TL hero (ön planda, kompakt) -->
          <tr>
            <td style="background-color:{C_CARD};border-left:1px solid rgba(255,213,62,0.12);border-right:1px solid rgba(255,213,62,0.12);padding:6px 24px 16px;">
              <table role="presentation" width="100%" cellspacing="0" cellpadding="0" border="0" style="background:linear-gradient(135deg,#12305c 0%,{C_BG} 100%);border-radius:12px;border:2px solid {C_GOLD};">
                <tr>
                  <td style="padding:18px 16px;text-align:center;">
                    <span style="display:inline-block;background:rgba(255,213,62,0.12);border:1px solid rgba(255,213,62,0.35);border-radius:999px;padding:4px 12px;font-size:9px;font-weight:700;color:{C_GOLD};text-transform:uppercase;letter-spacing:0.8px;">Yeni üyelere özel</span>
                    <div style="font-size:34px;font-weight:900;color:{C_GOLD};line-height:1.05;margin-top:10px;">3.000 TL</div>
                    <div style="font-size:15px;font-weight:800;color:{C_TEXT};margin-top:4px;letter-spacing:0.4px;">DENEME KASASI</div>
                    <p style="margin:10px 0 14px;font-size:12px;line-height:1.5;color:{C_MUTED};">Kayıt ol, deneme kasanı al ve risk almadan slot &amp; casino oyunlarını dene.</p>
                    <a href="{PROMO_LINK}" style="display:inline-block;background-color:{C_GOLD};color:{C_DARK};font-size:13px;font-weight:700;text-decoration:none;padding:11px 28px;border-radius:10px;">Hemen Başla</a>
                  </td>
                </tr>
              </table>
            </td>
          </tr>
          <!-- Promo grid -->
          <tr>
            <td style="background-color:{C_CARD};border-left:1px solid rgba(255,213,62,0.12);border-right:1px solid rgba(255,213,62,0.12);padding:4px 19px 14px;">
              <p style="margin:0 0 8px;font-size:10px;font-weight:700;color:{C_GOLD};text-transform:uppercase;letter-spacing:1px;">Diğer promosyonlar</p>
              {_promo_grid_html()}
            </td>
          </tr>
          <!-- CTA -->
          <tr>
            <td style="background-color:{C_CARD};border-left:1px solid rgba(255,213,62,0.12);border-right:1px solid rgba(255,213,62,0.12);padding:2px 24px 20px;text-align:center;">
              <a href="{PROMO_LINK}" style="display:inline-block;background-color:{C_GOLD};color:{C_DARK};font-size:14px;font-weight:700;text-decoration:none;padding:12px 32px;border-radius:10px;">Tüm Promosyonları Gör</a>
              <p style="margin:10px 0 0;font-size:10px;color:#6d7ea8;">makrobet804.com/tr/pages/promotions</p>
            </td>
          </tr>
          <!-- Footer -->
          <tr>
            <td style="background-color:#040f1f;border-radius:0 0 14px 14px;border:1px solid rgba(255,213,62,0.1);border-top:none;padding:14px 24px;text-align:center;">
              <p style="margin:0 0 5px;font-size:10px;color:#6d7ea8;line-height:1.5;">Bu e-posta sana özel bir davet olarak gönderilmiştir.</p>
              <p style="margin:0;font-size:9px;color:#4d5d7a;">18+ · Kumar bağımlılık yapabilir — sorumlu oyun.</p>
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


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
        return existing["id"]
    return insert_returning_id(
        conn,
        """
        INSERT INTO mail_templates (name, subject, html_body, text_body, created_at, updated_at)
        VALUES (?, ?, ?, ?, ?, ?)
        """,
        (DAVET_TEST_NAME, DAVET_TEST_SUBJECT, DAVET_TEST_HTML, DAVET_TEST_TEXT, now, now),
    )
