"""Makrobet 2026 mailing şablonları — site paleti + promo görselleri.

Logo: __MAIL_LOGO__ → /static/mailing/makrobet-logo-black.png
Görseller: __MB_IMG_*__ → /static/mailing/promos/*.jpg (siteden)
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

SEED_FLAG = "seeded_makrobet_templates_v2026c"

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
      <td align="center" style="padding:12px 18px;font-family:Arial,Helvetica,sans-serif;font-size:13px;line-height:1.45;color:#ffffff;">
        <strong style="color:{GOLD};">⚠ ÖNEMLİ:</strong>
        Bu mail Spam klasöründeyse <strong style="color:{GOLD};">butonlar çalışmaz</strong>.
        Önce <strong style="color:{GOLD};">Spam değil</strong> / <strong style="color:{GOLD};">Gelen kutusuna taşı</strong> deyin,
        sonra butonlara tıklayın.
      </td>
    </tr>
  </table>"""


def _logo():
    return (
        f'<a href="{CTA}" style="text-decoration:none;">'
        f'<img src="{LOGO}" alt="Makrobet" width="180" '
        f'style="display:block;margin:0 auto;border:0;max-width:180px;height:auto;"></a>'
    )


def _btn(label, pad="14px 28px"):
    return (
        f'<a href="{CTA}" style="display:inline-block;background:{GOLD};color:{DARK};'
        f"font-family:Arial,Helvetica,sans-serif;font-size:15px;font-weight:800;"
        f"text-decoration:none;padding:{pad};border-radius:10px;letter-spacing:0.02em;\">"
        f"{label}</a>"
    )


def _btn_row(label):
    return f"""
          <tr>
            <td align="center" style="padding:6px 24px 14px;">
              {_btn(label)}
            </td>
          </tr>"""


def _hero_img(src, alt):
    return f"""
          <tr>
            <td align="center" style="padding:4px 20px 12px;">
              <a href="{CTA}" style="text-decoration:none;">
                <img src="{src}" alt="{alt}" width="520"
                  style="display:block;width:100%;max-width:520px;height:auto;border:0;border-radius:14px;border:1px solid {BORDER};">
              </a>
            </td>
          </tr>"""


def _promo_visual(src, title, desc):
    return f"""
          <tr>
            <td style="padding:0 20px 12px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                style="background:{ROW};border:1px solid {BORDER};border-radius:14px;overflow:hidden;">
                <tr>
                  <td width="128" valign="top" style="padding:0;">
                    <a href="{CTA}" style="text-decoration:none;">
                      <img src="{src}" alt="{title}" width="128"
                        style="display:block;width:128px;max-width:128px;height:auto;border:0;">
                    </a>
                  </td>
                  <td valign="middle" style="padding:14px 16px;">
                    <div style="font-family:Arial,Helvetica,sans-serif;font-size:15px;font-weight:800;color:{GOLD};line-height:1.25;">{title}</div>
                    <div style="font-family:Arial,Helvetica,sans-serif;font-size:13px;color:{MUTED};line-height:1.45;margin-top:5px;">{desc}</div>
                    <div style="margin-top:10px;">{_btn("İncele →", "9px 16px")}</div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>"""


def _promo_text(num, title, desc):
    return f"""
          <tr>
            <td style="padding:0 20px 8px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0"
                style="background:{CARD};border:1px solid {BORDER};border-left:3px solid {GOLD};border-radius:10px;">
                <tr>
                  <td width="36" valign="top" style="padding:12px 0 12px 12px;">
                    <div style="width:24px;height:24px;border-radius:50%;background:rgba(255,212,0,0.14);border:1px solid rgba(255,212,0,0.45);text-align:center;line-height:24px;font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:800;color:{GOLD};">{num}</div>
                  </td>
                  <td style="padding:12px 14px 12px 6px;">
                    <a href="{CTA}" style="font-family:Arial,Helvetica,sans-serif;font-size:14px;font-weight:800;color:{GOLD};text-decoration:none;">{title}</a>
                    <div style="font-family:Arial,Helvetica,sans-serif;font-size:12px;color:{MUTED};line-height:1.45;margin-top:3px;">{desc}</div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>"""


def _chip_row(labels):
    chips = "".join(
        f'<td style="padding:3px;"><span style="display:inline-block;padding:7px 11px;border-radius:999px;'
        f"border:1px solid {BORDER};background:{ROW};color:{TEXT};font-family:Arial,Helvetica,sans-serif;"
        f'font-size:11px;font-weight:700;white-space:nowrap;">{lab}</span></td>'
        for lab in labels
    )
    return f"""
          <tr>
            <td align="center" style="padding:4px 16px 14px;">
              <table role="presentation" cellpadding="0" cellspacing="0"><tr>{chips}</tr></table>
            </td>
          </tr>"""


def _shell(eyebrow, headline, lead_html, body_rows, cta1, cta2, hero_src="", hero_alt=""):
    hero = _hero_img(hero_src, hero_alt) if hero_src else ""
    return f"""<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>{headline}</title>
</head>
<body style="margin:0;padding:0;background:{INK};">
{_spam()}
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" style="background:{INK};">
    <tr>
      <td align="center" style="padding:22px 10px 36px;">
        <table role="presentation" width="600" cellpadding="0" cellspacing="0"
          style="width:100%;max-width:600px;background:{BG};border:1px solid {BORDER};border-radius:18px;overflow:hidden;">
          <tr><td style="height:4px;background:{GOLD};font-size:0;line-height:0;">&nbsp;</td></tr>
          <tr><td align="center" style="padding:22px 24px 8px;">{_logo()}</td></tr>
          <tr>
            <td align="center" style="padding:0 24px 6px;font-family:Arial,Helvetica,sans-serif;font-size:11px;font-weight:800;letter-spacing:0.16em;text-transform:uppercase;color:{GOLD};">
              {eyebrow}
            </td>
          </tr>
          <tr>
            <td align="center" style="padding:0 22px 10px;font-family:Georgia,'Times New Roman',serif;font-size:26px;line-height:1.2;font-weight:700;color:#ffffff;letter-spacing:-0.02em;">
              {headline}
            </td>
          </tr>
{hero}
{_btn_row(cta1)}
          <tr>
            <td style="padding:4px 24px 12px;font-family:Arial,Helvetica,sans-serif;font-size:14px;line-height:1.6;color:{TEXT};">
              {lead_html}
            </td>
          </tr>
{body_rows}
{_chip_row(["Bilet Etkinliği", "Makro Kasa", "Makro Manager", "Prim Bonusu", "Çevrim Bonusu"])}
{_btn_row(cta2)}
          <tr>
            <td align="center" style="padding:0 24px 8px;">
              <a href="{CTA}" style="font-family:Arial,Helvetica,sans-serif;font-size:12px;font-weight:700;color:{GOLD};text-decoration:underline;">
                {AFF}
              </a>
            </td>
          </tr>
          <tr>
            <td style="padding:10px 24px 20px;font-family:Arial,Helvetica,sans-serif;font-size:11px;line-height:1.5;color:{MUTED};text-align:center;">
              Spam klasöründeyken butonlar kilitlidir — Spam değil deyip tekrar deneyin.<br>
              18+ · Sorumlu oyun · Şartlar geçerlidir · Makrobet
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


TEMPLATES = [
    {
        "name": "2026 · Davet Mailingi",
        "subject": "{{name}}, Makrobet'te seni 3.000 TL deneme kasası bekliyor!",
        "html_body": _shell(
            "Özel davet · deneme kasası",
            "3.000 TL deneme kasası seni bekliyor",
            "Merhaba <strong style='color:#fff;'>{{name}}</strong>,<br><br>"
            "Makrobet’e özel davetlisin. Kayıt ol, <strong style='color:#ffd400;'>3.000 TL deneme kasanı</strong> aç "
            "ve aşağıdaki canlı kampanyalarla devam et.",
            _promo_visual(IMG_KASA, "3.000 TL Deneme Kasası", "Yeni üyelere özel başlangıç kasası — görseldeki kasa seni bekliyor.")
            + _promo_visual(IMG_ARKADAS, "Arkadaşını Getir", "Arkadaşının aldığı yatırım bonusunu sana da ekleyelim.")
            + _promo_visual(IMG_KAYIP, "%100 Kayıp Bonusu", "Sıfır riskle yatırım senden, güvence Makrobet’ten.")
            + _promo_visual(IMG_RACE, "Amusnet Race", "Ödül havuzlu yarışta zirveye oyna.")
            + _promo_text("5", "Bilet Etkinliği", "Etkinlik biletlerini topla, özel çekiliş / ödül turlarına gir.")
            + _promo_text("6", "Makro Manager · Prim · Çevrim", "Manager rolling, prim ve çevrim bonuslarıyla bakiyeni büyüt."),
            "Hemen Kayıt Ol",
            "Kuponu / Kasayı Aç",
            IMG_KASA,
            "Makrobet Deneme Kasası",
        ),
        "text_body": (
            "Merhaba {{name}},\n\n"
            "3.000 TL deneme kasası + Arkadaşını Getir, %100 Kayıp, Race, Bilet, Makro Manager, Prim, Çevrim.\n\n"
            f"Spam değil deyip tıkla: {AFF}\n\n18+ Makrobet"
        ),
    },
    {
        "name": "2026 · Pasif Üye Geri Getirme",
        "subject": "{{name}}, hesabın seni bekliyor — kasa ve bonuslar hazır",
        "html_body": _shell(
            "Geri dönüş · özel seçki",
            "Seni özledik — dönüş paketini aç",
            "Merhaba <strong style='color:#fff;'>{{name}}</strong>,<br><br>"
            "Bir süredir yoktun. Promosyonlar sayfasından seçtiğimiz "
            "<strong style='color:#ffd400;'>kasa, kayıp ve etkinlik</strong> fırsatlarıyla geri dön.",
            _promo_visual(IMG_KAYIP, "%100 Kayıp Bonusu", "Sıfır riskli güvence — yatırıma güvenle dön.")
            + _promo_visual(IMG_KASA, "Makro Kasa", "Yatırımına ek kasa / ekstra ödül penceresi.")
            + _promo_visual(IMG_RACE, "Amusnet Race", "Ödüllü yarışta yerini geri al.")
            + _promo_text("4", "Bilet Etkinliği", "Bilet topla, etkinlik ödüllerine katıl.")
            + _promo_text("5", "Makro Manager", "Manager rolling ile toplu etkinlik avantajı.")
            + _promo_text("6", "Prim & Çevrim Bonusu", "Aktif dönem prim / çevrim kampanyaları."),
            "Hesabıma Dön",
            "Bonusları Gör",
            IMG_KAYIP,
            "Kayıp Bonusu",
        ),
        "text_body": (
            "Merhaba {{name}},\n\n"
            "Geri dönüş: %100 Kayıp, Makro Kasa, Race, Bilet, Manager, Prim, Çevrim.\n\n"
            f"{AFF}\n\n18+ Makrobet"
        ),
    },
    {
        "name": "2026 · Memnuniyet Bonusu",
        "subject": "{{name}}, senin için memnuniyet jesti + kasa fırsatları",
        "html_body": _shell(
            "Memnuniyet · özel jest",
            "Senin için ekstra bir jest yaptık",
            "Merhaba <strong style='color:#fff;'>{{name}}</strong>,<br><br>"
            "Yakın zamanda yatırımın oldu ama çekim tarafında aksaklık yaşadıysan — "
            "<strong style='color:#ffd400;'>memnuniyet bonusun</strong> tanımlı. "
            "Yanına da sitedeki güçlü kampanyaları ekledik.",
            _promo_text("1", "Memnuniyet Bonusu", "Çekim/deneyim aksamalarına özel jest — hesabını kontrol et / destekten talep et.")
            + _promo_visual(IMG_KAYIP, "%100 Kayıp Bonusu", "Riski Makrobet üstlensin.")
            + _promo_visual(IMG_KASA, "Makro Kasa", "Ek kasa ile moralini yükselt.")
            + _promo_text("4", "Prim · Çevrim · Manager", "Prim, çevrim ve Makro Manager fırsatları aktif.")
            + _promo_text("5", "Bilet Etkinliği", "Etkinlik biletleriyle ekstra ödül şansı."),
            "Bonusu Kontrol Et",
            "Siteye Git",
            IMG_KASA,
            "Makro Kasa",
        ),
        "text_body": (
            "Merhaba {{name}},\n\n"
            "Memnuniyet jesti + %100 Kayıp, Makro Kasa, Prim, Çevrim, Manager, Bilet.\n\n"
            f"{AFF}\n\n18+ Makrobet"
        ),
    },
    {
        "name": "2026 · Yeni Üye İlk Yatırım",
        "subject": "{{name}}, ilk yatırımın için kasa ve bonus paketleri",
        "html_body": _shell(
            "İlk adım · yatırım",
            "Deneme bitti — kasanı büyütme zamanı",
            "Merhaba <strong style='color:#fff;'>{{name}}</strong>,<br><br>"
            "Üyeliğin hazır. İlk yatırımını yapıp "
            "<strong style='color:#ffd400;'>Makro Kasa, Race ve prim/çevrim</strong> paketlerini açmana tek adım kaldı.",
            _promo_visual(IMG_KASA, "Makro Kasa / Yatırım Ekstra", "İlk yatırımlara ek kasa fırsatı.")
            + _promo_visual(IMG_KAYIP, "%100 Kayıp Güvencesi", "İlk adımını daha rahat at.")
            + _promo_visual(IMG_RACE, "Amusnet Race", "Ödül yarışına erken katıl.")
            + _promo_text("4", "Prim Bonusu", "Yatırımına prim katmanı.")
            + _promo_text("5", "Çevrim Bonusu", "Çevrim kampanyalarıyla avantaj yakala.")
            + _promo_text("6", "Bilet · Makro Manager", "Bilet etkinliği ve manager rolling."),
            "İlk Yatırımı Yap",
            "Kampanyaları Aç",
            IMG_KASA,
            "Yatırım Kasası",
        ),
        "text_body": (
            "Merhaba {{name}},\n\n"
            "İlk yatırım: Makro Kasa, Kayıp, Race, Prim, Çevrim, Bilet, Manager.\n\n"
            f"{AFF}\n\n18+ Makrobet"
        ),
    },
    {
        "name": "2026 · Turnuva & Bilet Etkinlikleri",
        "subject": "{{name}}, Race · Bilet · Makro Manager seni bekliyor",
        "html_body": _shell(
            "Etkinlik arenası",
            "Bu haftanın sahnesi: Race, Bilet, Manager",
            "Merhaba <strong style='color:#fff;'>{{name}}</strong>,<br><br>"
            "Klasik bonusun ötesinde — <strong style='color:#ffd400;'>turnuva, bilet ve Makro Manager</strong> "
            "etkinlikleriyle ödül havuzlarına katıl.",
            _promo_visual(IMG_RACE, "Amusnet Race", "Ödül havuzlu yarış — liderlik için erken gir.")
            + _promo_text("2", "Bilet Etkinliği", "Biletleri topla, özel çekiliş / ödül turlarına gir.")
            + _promo_text("3", "Makro Manager", "Manager rolling / toplu etkinlik çarpanı.")
            + _promo_visual(IMG_KASA, "Makro Kasa", "Etkinlik döneminde ek kasa fırsatları.")
            + _promo_text("5", "Prim & Çevrim Bonusu", "Etkinlik saatlerinde prim / çevrim avantajı.")
            + _promo_visual(IMG_ARKADAS, "Arkadaşını Getir", "Ekibini büyüt, ekstra ödül kap."),
            "Etkinliklere Katıl",
            "Hemen Oyna",
            IMG_RACE,
            "Amusnet Race",
        ),
        "text_body": (
            "Merhaba {{name}},\n\n"
            "Race, Bilet Etkinliği, Makro Manager, Makro Kasa, Prim, Çevrim, Arkadaşını Getir.\n\n"
            f"{AFF}\n\n18+ Makrobet"
        ),
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
