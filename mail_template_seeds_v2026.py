"""Makrobet 2026 mailing şablonları — hafif, güncel logo, çalışan Vipmail CTA.

Logo: __MAIL_LOGO__ → makrobet-logo-mail.jpg (güncel renkli)
Görseller: max 1–2 küçük jpg / mail
CTA: {{link:sc:https://makrovip.com/Vipmail}}
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

SEED_FLAG = "seeded_makrobet_templates_v2026d"

AFF = "https://makrovip.com/Vipmail"
CTA = "{{link:sc:https://makrovip.com/Vipmail}}"

BG = "#061c3d"
CARD = "#0a2448"
ROW = "#0f2d55"
TEXT = "#e6f0fe"
MUTED = "#9db3d4"
GOLD = "#ffd400"
BORDER = "#2a4a7a"
INK = "#040e1f"
DARK = "#0f1328"

LOGO = "__MAIL_LOGO__"
IMG_KASA = "__MB_IMG_KASA__"
IMG_KAYIP = "__MB_IMG_KAYIP__"
IMG_ARKADAS = "__MB_IMG_ARKADAS__"
IMG_RACE = "__MB_IMG_RACE__"


def _spam():
    return f"""
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:#1a0a00;border-bottom:2px solid {GOLD};">
    <tr>
      <td align="center" style="padding:11px 16px;font-family:Arial,Helvetica,sans-serif;font-size:12px;line-height:1.4;color:#fff;">
        <strong style="color:{GOLD};">⚠</strong>
        Spam klasöründeyse <strong style="color:{GOLD};">butonlar çalışmaz</strong>.
        Önce <strong style="color:{GOLD};">Spam değil</strong> deyin, sonra tıklayın.
      </td>
    </tr>
  </table>"""


def _logo():
    return (
        f'<a href="{CTA}" target="_blank" rel="noopener" style="text-decoration:none;">'
        f'<img src="{LOGO}" alt="Makrobet" width="168" '
        f'style="display:block;margin:0 auto;border:0;max-width:168px;height:auto;"></a>'
    )


def _btn(label):
    return (
        f'<a href="{CTA}" target="_blank" rel="noopener" '
        f'style="display:inline-block;background:{GOLD};color:{DARK};'
        f"font-family:Arial,Helvetica,sans-serif;font-size:14px;font-weight:800;"
        f'text-decoration:none;padding:13px 26px;border-radius:10px;">{label}</a>'
    )


def _btn_row(label):
    return f"""
          <tr><td align="center" style="padding:4px 20px 12px;">{_btn(label)}</td></tr>
          <tr><td align="center" style="padding:0 20px 10px;font-family:Arial,Helvetica,sans-serif;font-size:11px;">
            <a href="{CTA}" target="_blank" rel="noopener" style="color:{GOLD};font-weight:700;">{AFF}</a>
          </td></tr>"""


def _hero(src, alt):
    return f"""
          <tr>
            <td align="center" style="padding:2px 18px 10px;">
              <a href="{CTA}" target="_blank" rel="noopener">
                <img src="{src}" alt="{alt}" width="280"
                  style="display:block;width:280px;max-width:70%;height:auto;border:0;border-radius:12px;border:1px solid {BORDER};">
              </a>
            </td>
          </tr>"""


def _row(title, desc):
    return f"""
          <tr>
            <td style="padding:0 18px 7px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                style="background:{ROW};border:1px solid {BORDER};border-left:3px solid {GOLD};border-radius:8px;">
                <tr>
                  <td style="padding:11px 12px;">
                    <a href="{CTA}" target="_blank" rel="noopener"
                      style="font-family:Arial,Helvetica,sans-serif;font-size:13px;font-weight:800;color:{GOLD};text-decoration:none;">{title}</a>
                    <div style="font-family:Arial,Helvetica,sans-serif;font-size:12px;color:{MUTED};line-height:1.4;margin-top:3px;">{desc}</div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>"""


def _chips():
    labs = ["Bilet Etkinliği", "Makro Kasa", "Makro Manager", "Prim", "Çevrim", "Race"]
    cells = "".join(
        f'<td style="padding:2px;"><span style="display:inline-block;padding:5px 8px;border-radius:999px;'
        f"border:1px solid {BORDER};background:{CARD};color:{TEXT};font-family:Arial,Helvetica,sans-serif;"
        f'font-size:10px;font-weight:700;">{x}</span></td>'
        for x in labs
    )
    return f"""
          <tr><td align="center" style="padding:2px 12px 10px;">
            <table role="presentation" cellpadding="0" cellspacing="0"><tr>{cells}</tr></table>
          </td></tr>"""


def _shell(eyebrow, headline, lead, rows, cta, hero_src="", hero_alt=""):
    hero = _hero(hero_src, hero_alt) if hero_src else ""
    return f"""<!DOCTYPE html>
<html lang="tr"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">
<title>{headline}</title></head>
<body style="margin:0;padding:0;background:{INK};">
{_spam()}
<table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{INK};"><tr>
<td align="center" style="padding:16px 8px 28px;">
<table role="presentation" width="560" cellpadding="0" cellspacing="0" style="width:100%;max-width:560px;background:{BG};border:1px solid {BORDER};border-radius:14px;overflow:hidden;">
<tr><td style="height:3px;background:{GOLD};font-size:0;line-height:0;">&nbsp;</td></tr>
<tr><td align="center" style="padding:18px 18px 6px;">{_logo()}</td></tr>
<tr><td align="center" style="padding:0 16px 4px;font-family:Arial,Helvetica,sans-serif;font-size:10px;font-weight:800;letter-spacing:0.14em;text-transform:uppercase;color:{GOLD};">{eyebrow}</td></tr>
<tr><td align="center" style="padding:0 16px 8px;font-family:Georgia,'Times New Roman',serif;font-size:22px;line-height:1.25;font-weight:700;color:#fff;">{headline}</td></tr>
{hero}
{_btn_row(cta)}
<tr><td style="padding:2px 18px 10px;font-family:Arial,Helvetica,sans-serif;font-size:13px;line-height:1.55;color:{TEXT};">{lead}</td></tr>
{rows}
{_chips()}
{_btn_row(cta)}
<tr><td style="padding:6px 16px 16px;font-family:Arial,Helvetica,sans-serif;font-size:10px;line-height:1.45;color:{MUTED};text-align:center;">
Spam’de butonlar kilitli · Spam değil deyip tekrar dene<br>18+ · Makrobet · {AFF}
</td></tr>
</table></td></tr></table>
</body></html>"""


TEMPLATES = [
    {
        "name": "2026 · Davet Mailingi",
        "subject": "{{name}}, Makrobet'te seni 3.000 TL deneme kasası bekliyor!",
        "html_body": _shell(
            "Özel davet",
            "3.000 TL deneme kasası seni bekliyor",
            "Merhaba <strong style='color:#fff;'>{{name}}</strong> — kayıt ol, deneme kasanı aç. "
            "Aşağıdaki kampanyalar da aktif.",
            _row("3.000 TL Deneme Kasası", "Yeni üye başlangıç kasası")
            + _row("Arkadaşını Getir", "Arkadaşının yatırım bonusunu sen de al")
            + _row("%100 Kayıp Bonusu", "Sıfır risk — güvence Makrobet’ten")
            + _row("Amusnet Race · Bilet · Manager", "Yarış, bilet etkinliği, Makro Manager")
            + _row("Prim & Çevrim Bonusu", "Aktif prim / çevrim kampanyaları"),
            "Hemen Kayıt Ol",
            IMG_KASA,
            "Deneme Kasası",
        ),
        "text_body": f"Merhaba {{{{name}}}},\n\n3.000 TL deneme kasası + promosyonlar.\nSpam değil deyip tıkla: {AFF}\n",
    },
    {
        "name": "2026 · Pasif Üye Geri Getirme",
        "subject": "{{name}}, hesabın seni bekliyor — kasa ve bonuslar hazır",
        "html_body": _shell(
            "Geri dönüş",
            "Seni özledik — dönüş paketini aç",
            "Merhaba <strong style='color:#fff;'>{{name}}</strong> — %100 kayıp, kasa, race ve manager ile geri dön.",
            _row("%100 Kayıp Bonusu", "Güvenli geri dönüş")
            + _row("Makro Kasa", "Yatırıma ek kasa")
            + _row("Amusnet Race", "Ödül havuzlu yarış")
            + _row("Bilet · Makro Manager", "Etkinlik + rolling")
            + _row("Prim & Çevrim", "Aktif dönem bonusları"),
            "Hesabıma Dön",
            IMG_KAYIP,
            "Kayıp Bonusu",
        ),
        "text_body": f"Merhaba {{{{name}}}},\n\nGeri dönüş paketleri hazır.\n{AFF}\n",
    },
    {
        "name": "2026 · Memnuniyet Bonusu",
        "subject": "{{name}}, senin için memnuniyet jesti hazır",
        "html_body": _shell(
            "Memnuniyet",
            "Senin için ekstra bir jest",
            "Merhaba <strong style='color:#fff;'>{{name}}</strong> — çekim aksamalarına özel memnuniyet jesti + sitedeki güçlü kampanyalar.",
            _row("Memnuniyet Bonusu", "Özel jest — hesabını kontrol et")
            + _row("%100 Kayıp Bonusu", "Risk Makrobet’te")
            + _row("Makro Kasa", "Ek kasa fırsatı")
            + _row("Prim · Çevrim · Manager · Bilet", "Aktif etkinlik seti"),
            "Bonusu Kontrol Et",
            IMG_KASA,
            "Makro Kasa",
        ),
        "text_body": f"Merhaba {{{{name}}}},\n\nMemnuniyet jesti + kampanyalar.\n{AFF}\n",
    },
    {
        "name": "2026 · Yeni Üye İlk Yatırım",
        "subject": "{{name}}, ilk yatırımın için kasa paketleri",
        "html_body": _shell(
            "İlk yatırım",
            "Kasanı büyütme zamanı",
            "Merhaba <strong style='color:#fff;'>{{name}}</strong> — ilk yatırımınla Makro Kasa, Race, prim ve çevrimi aç.",
            _row("Makro Kasa", "Yatırıma ekstra kasa")
            + _row("%100 Kayıp Güvencesi", "Rahat ilk adım")
            + _row("Amusnet Race", "Ödül yarışı")
            + _row("Prim · Çevrim · Bilet · Manager", "Tam paket"),
            "İlk Yatırımı Yap",
            IMG_KASA,
            "Yatırım Kasası",
        ),
        "text_body": f"Merhaba {{{{name}}}},\n\nİlk yatırım paketleri.\n{AFF}\n",
    },
    {
        "name": "2026 · Turnuva & Bilet Etkinlikleri",
        "subject": "{{name}}, Race · Bilet · Makro Manager seni bekliyor",
        "html_body": _shell(
            "Etkinlik",
            "Race, Bilet, Manager bu hafta sahnede",
            "Merhaba <strong style='color:#fff;'>{{name}}</strong> — turnuva ve toplu etkinliklere katıl.",
            _row("Amusnet Race", "Ödül havuzlu yarış")
            + _row("Bilet Etkinliği", "Bilet topla, ödül turuna gir")
            + _row("Makro Manager", "Manager rolling")
            + _row("Makro Kasa · Prim · Çevrim", "Etkinlik destek paketleri")
            + _row("Arkadaşını Getir", "Ekibini büyüt"),
            "Etkinliklere Katıl",
            IMG_RACE,
            "Amusnet Race",
        ),
        "text_body": f"Merhaba {{{{name}}}},\n\nRace / Bilet / Manager.\n{AFF}\n",
    },
]


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
                    (item["subject"], item.get("html_body") or "", item.get("text_body") or "", now, exists["id"]),
                )
                updated += 1
            continue
        insert_returning_id(
            conn,
            """
            INSERT INTO mail_templates (name, subject, html_body, text_body, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (name, item["subject"], item.get("html_body") or "", item.get("text_body") or "", now, now),
        )
        added += 1
    upsert_mail_setting(conn, SEED_FLAG, "1")
    try:
        conn.commit()
    except Exception:
        pass
    return {"added": added, "updated": updated}
