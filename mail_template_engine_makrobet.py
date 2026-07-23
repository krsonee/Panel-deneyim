"""Makrobet unified HTML email template engine.

Modular, table-based, 600px fluid layouts for major clients
(Apple Mail / Gmail / Outlook). Six campaign presets share one
component kit + design tokens.

Placeholders resolved at send/preview time:
  __MAIL_LOGO__, __MB_IMG_KASA__, __MB_IMG_KAYIP__, __MB_IMG_ARKADAS__, __MB_IMG_RACE__
  {{name}}, {{link:sc:https://makrovip.com/Vipmail}}
"""

from __future__ import annotations

from typing import Iterable, Sequence

# ── Design tokens ──────────────────────────────────────────────────────────
BG = "#08142c"
CARD = "#102244"
ROW = "#132a52"
TEXT = "#ffffff"
MUTED = "#94a3b8"
GOLD = "#ffcc00"
GOLD_SOFT = "rgba(245, 158, 11, 0.1)"
BORDER = "#243b63"
INK = "#08142c"
CTA_INK = "#08142c"

FONT = "'Inter', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, Helvetica, Arial, sans-serif"
MAX_W = 600

AFF = "https://makrovip.com/Vipmail"
CTA = "{{link:sc:https://makrovip.com/Vipmail}}"

LOGO = "__MAIL_LOGO__"
IMG_KASA = "__MB_IMG_KASA__"
IMG_KAYIP = "__MB_IMG_KAYIP__"
IMG_ARKADAS = "__MB_IMG_ARKADAS__"
IMG_RACE = "__MB_IMG_RACE__"

TAG_PILLS = (
    "Bilet Etkinliği",
    "Makro Kasa",
    "Makro Manager",
    "Prim",
    "Çevrim",
    "Race",
)


# ── Components ─────────────────────────────────────────────────────────────
def notice_spam() -> str:
    """Soft amber notice — rgba for modern clients, solid fallback for Outlook."""
    # Approx navy+#f59e0b @ 10% → #1a1608-ish; keep rgba in style as requested
    solid_fallback = "#1a1608"
    return f"""
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
    <tr>
      <td align="center" style="padding:0 12px 12px;">
        <table role="presentation" width="{MAX_W}" cellpadding="0" cellspacing="0" border="0"
          bgcolor="{solid_fallback}"
          style="width:100%;max-width:{MAX_W}px;background-color:{GOLD_SOFT};background:{GOLD_SOFT};
          border:1px solid rgba(255,204,0,0.35);border-radius:12px;">
          <tr>
            <td align="center" bgcolor="{solid_fallback}"
              style="padding:12px 16px;font-family:{FONT};font-size:12px;line-height:1.5;color:{GOLD};
              background-color:{GOLD_SOFT};">
              Spam klasöründeyse <strong style="color:{GOLD};">butonlar çalışmaz</strong>.
              Önce <strong style="color:{GOLD};">Spam değil</strong> deyin, sonra tıklayın.
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>"""


def logo_block(width: int = 168) -> str:
    return (
        f'<a href="{CTA}" target="_blank" rel="noopener" style="text-decoration:none;">'
        f'<img src="{LOGO}" alt="Makrobet" width="{width}" '
        f'style="display:block;margin:0 auto;border:0;outline:none;'
        f'max-width:{width}px;width:{width}px;height:auto;"></a>'
    )


def badge(label: str, *, solid: bool = True) -> str:
    if solid:
        return (
            f'<span style="display:inline-block;background:{GOLD};color:{CTA_INK};'
            f"font-family:{FONT};font-size:11px;font-weight:800;letter-spacing:0.08em;"
            f'text-transform:uppercase;padding:6px 14px;border-radius:999px;">{label}</span>'
        )
    return (
        f'<span style="display:inline-block;background:{GOLD_SOFT};color:{GOLD};'
        f"font-family:{FONT};font-size:11px;font-weight:800;letter-spacing:0.08em;"
        f"text-transform:uppercase;padding:6px 14px;border-radius:999px;"
        f'border:1px solid rgba(255,204,0,0.4);">{label}</span>'
    )


def cta_button(label: str) -> str:
    """Primary CTA only — no exposed raw affiliate URL under the button."""
    return (
        f'<a href="{CTA}" target="_blank" rel="noopener" '
        f'style="display:inline-block;background:{GOLD};color:{CTA_INK};'
        f"font-family:{FONT};font-size:15px;font-weight:800;"
        f"text-decoration:none;padding:14px 28px;border-radius:12px;"
        f'border:0;mso-padding-alt:0;">'
        f"<!--[if mso]><i style=\"letter-spacing:28px;mso-font-width:-100%;mso-text-raise:21pt;\">&nbsp;</i><![endif]-->"
        f'<span style="mso-text-raise:10pt;">{label}</span>'
        f"<!--[if mso]><i style=\"letter-spacing:28px;mso-font-width:-100%;\">&nbsp;</i><![endif]-->"
        f"</a>"
    )


def cta_row(label: str) -> str:
    return f"""
          <tr>
            <td align="center" style="padding:6px 20px 16px;">
              {cta_button(label)}
            </td>
          </tr>"""


def hero_image(src: str, alt: str, width: int = 320) -> str:
    """Rounded hero — navy blend, no black plate / hard gold frame."""
    return f"""
          <tr>
            <td align="center" style="padding:4px 20px 12px;background:{BG};">
              <a href="{CTA}" target="_blank" rel="noopener" style="text-decoration:none;">
                <img src="{src}" alt="{alt}" width="{width}"
                  style="display:block;width:100%;max-width:{width}px;height:auto;border:0;outline:none;
                  border-radius:16px;background:{BG};">
              </a>
            </td>
          </tr>"""


def eyebrow(text: str) -> str:
    return f"""
          <tr>
            <td align="center" style="padding:0 20px 6px;font-family:{FONT};font-size:11px;
              font-weight:800;letter-spacing:0.14em;text-transform:uppercase;color:{GOLD};">{text}</td>
          </tr>"""


def headline(text: str) -> str:
    return f"""
          <tr>
            <td align="center" style="padding:0 20px 10px;font-family:{FONT};font-size:24px;
              line-height:1.25;font-weight:800;color:{TEXT};">{text}</td>
          </tr>"""


def lead(text: str) -> str:
    return f"""
          <tr>
            <td style="padding:2px 22px 12px;font-family:{FONT};font-size:14px;
              line-height:1.6;color:{MUTED};text-align:center;">{text}</td>
          </tr>"""


def feature_box_3000() -> str:
    return f"""
          <tr>
            <td style="padding:4px 20px 14px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
                style="background:{CARD};border-radius:16px;border:2px solid {GOLD};">
                <tr>
                  <td align="center" style="padding:22px 16px;">
                    <div style="font-family:{FONT};font-size:11px;font-weight:800;color:{GOLD};
                      letter-spacing:0.12em;text-transform:uppercase;">★ Yeni üyelere özel ★</div>
                    <div style="font-family:{FONT};font-size:36px;font-weight:900;color:{GOLD};
                      line-height:1;margin-top:8px;">3.000 TL</div>
                    <div style="font-family:{FONT};font-size:16px;font-weight:800;color:{TEXT};
                      letter-spacing:0.04em;margin-top:6px;">DENEME KASASI</div>
                    <div style="font-family:{FONT};font-size:13px;line-height:1.5;color:{MUTED};
                      margin-top:10px;max-width:380px;">Kayıt ol, deneme kasanı al — risk almadan başla.</div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>"""


def promo_card(title: str, desc: str, *, left_border: bool = True) -> str:
    border_left = f"border-left:3px solid {GOLD};" if left_border else ""
    return f"""
          <tr>
            <td style="padding:0 20px 8px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
                style="background:{ROW};border:1px solid {BORDER};{border_left}border-radius:12px;">
                <tr>
                  <td style="padding:12px 14px;">
                    <a href="{CTA}" target="_blank" rel="noopener"
                      style="font-family:{FONT};font-size:14px;font-weight:800;color:{GOLD};text-decoration:none;">{title}</a>
                    <div style="font-family:{FONT};font-size:12px;color:{MUTED};line-height:1.45;margin-top:4px;">{desc}</div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>"""


def numbered_promo(n: int, title: str, desc: str) -> str:
    return f"""
          <tr>
            <td style="padding:0 20px 8px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
                style="background:{ROW};border:1px solid {BORDER};border-left:3px solid {GOLD};border-radius:12px;">
                <tr>
                  <td width="40" valign="top" style="padding:12px 0 12px 12px;">
                    <div style="width:26px;height:26px;border-radius:50%;background:{GOLD_SOFT};
                      border:1px solid rgba(255,204,0,0.45);text-align:center;line-height:26px;
                      font-family:{FONT};font-size:12px;font-weight:800;color:{GOLD};">{n}</div>
                  </td>
                  <td valign="top" style="padding:11px 14px 11px 4px;">
                    <div style="font-family:{FONT};font-size:13px;font-weight:800;color:{GOLD};line-height:1.3;">{title}</div>
                    <div style="font-family:{FONT};font-size:12px;color:{MUTED};margin-top:3px;line-height:1.45;">{desc}</div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>"""


def promo_cards(items: Sequence[tuple[str, str]], *, left_border: bool = True) -> str:
    return "".join(promo_card(t, d, left_border=left_border) for t, d in items)


def numbered_list(items: Sequence[tuple[str, str]]) -> str:
    return "".join(numbered_promo(i, t, d) for i, (t, d) in enumerate(items, 1))


def tag_pills(labels: Iterable[str] = TAG_PILLS) -> str:
    labs = list(labels)
    # two rows of 3 for mobile readability
    chunks = [labs[i : i + 3] for i in range(0, len(labs), 3)]
    rows = []
    for chunk in chunks:
        cells = "".join(
            f'<td style="padding:3px;">'
            f'<span style="display:inline-block;padding:6px 10px;border-radius:999px;'
            f"border:1px solid {BORDER};background:{CARD};color:{TEXT};"
            f'font-family:{FONT};font-size:10px;font-weight:700;">{lab}</span></td>'
            for lab in chunk
        )
        rows.append(f"<tr>{cells}</tr>")
    return f"""
          <tr>
            <td align="center" style="padding:4px 16px 14px;">
              <table role="presentation" cellpadding="0" cellspacing="0" border="0">
                {''.join(rows)}
              </table>
            </td>
          </tr>"""


def footer_legal() -> str:
    """Legal footer — no raw affiliate URL text."""
    return f"""
          <tr>
            <td align="center" style="padding:8px 20px 22px;font-family:{FONT};font-size:11px;
              line-height:1.5;color:{MUTED};border-top:1px solid {BORDER};">
              Spam’de butonlar kilitli · Spam değil deyip tekrar dene<br>
              18+ · Sorumlu oyun · Makrobet
            </td>
          </tr>"""


def shell(
    *,
    title: str,
    body_rows: str,
    preheader: str = "",
) -> str:
    pre = (
        f'<div style="display:none;font-size:1px;line-height:1px;max-height:0;max-width:0;'
        f'opacity:0;overflow:hidden;mso-hide:all;">{preheader}&nbsp;&#847;&nbsp;&#847;</div>'
        if preheader
        else ""
    )
    return f"""<!DOCTYPE html>
<html lang="tr" xmlns="http://www.w3.org/1999/xhtml" xmlns:v="urn:schemas-microsoft-com:vml" xmlns:o="urn:schemas-microsoft-com:office:office">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="X-UA-Compatible" content="IE=edge">
  <meta name="x-apple-disable-message-reformatting">
  <meta name="color-scheme" content="dark">
  <meta name="supported-color-schemes" content="dark">
  <title>{title}</title>
  <!--[if mso]>
  <noscript>
    <xml>
      <o:OfficeDocumentSettings>
        <o:AllowPNG/>
        <o:PixelsPerInch>96</o:PixelsPerInch>
      </o:OfficeDocumentSettings>
    </xml>
  </noscript>
  <style>table,td{{font-family:Segoe UI,Arial,sans-serif !important;}}</style>
  <![endif]-->
  <style type="text/css">
    body,table,td,a{{-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%;}}
    table,td{{mso-table-lspace:0pt;mso-table-rspace:0pt;border-collapse:collapse;}}
    img{{-ms-interpolation-mode:bicubic;border:0;height:auto;line-height:100%;outline:none;text-decoration:none;}}
    body{{margin:0 !important;padding:0 !important;width:100% !important;background:{INK};}}
    a[x-apple-data-detectors]{{color:inherit !important;text-decoration:none !important;}}
    @media only screen and (max-width:620px){{
      .mb-shell{{width:100% !important;}}
      .mb-pad{{padding-left:14px !important;padding-right:14px !important;}}
    }}
  </style>
</head>
<body style="margin:0;padding:0;background-color:{INK};font-family:{FONT};">
  {pre}
  {notice_spam()}
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:{INK};">
    <tr>
      <td align="center" style="padding:8px 10px 32px;">
        <table role="presentation" class="mb-shell" width="{MAX_W}" cellpadding="0" cellspacing="0" border="0"
          style="width:100%;max-width:{MAX_W}px;background:{BG};border:1px solid {BORDER};border-radius:16px;overflow:hidden;">
          <tr><td style="height:3px;line-height:3px;font-size:0;background:{GOLD};">&nbsp;</td></tr>
          <tr>
            <td align="center" style="padding:22px 20px 10px;background:{BG};">
              {logo_block()}
            </td>
          </tr>
          {body_rows}
          {footer_legal()}
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


# ── Preset builders ────────────────────────────────────────────────────────
def preset_davet_test() -> dict:
    items = [
        ("%100 Kayıp Bonusu", "Sıfır risk — güvence Makrobet’ten."),
        ("Arkadaşını Getir", "Arkadaşının yatırım bonusunu sen de al."),
        ("Amusnet Race · Bilet · Manager", "Yarış, bilet etkinliği ve Makro Manager."),
    ]
    body = (
        f"""
          <tr><td align="center" style="padding:4px 20px 10px;">{badge("DENEME BONUSU")}</td></tr>
        """
        + eyebrow("Özel davet")
        + headline("Merhaba {{name}}, seni 3.000 TL deneme kasası bekliyor")
        + lead("Makrobet’te güncel promosyonlar ve hızlı ödeme seni bekliyor.")
        + feature_box_3000()
        + f"""
          <tr>
            <td style="padding:0 22px 8px;font-family:{FONT};font-size:11px;font-weight:800;
              letter-spacing:0.1em;text-transform:uppercase;color:{GOLD};">Diğer promosyonlar</td>
          </tr>
        """
        + numbered_list(items)
        + cta_row("Deneme Bonusu Al")
    )
    return {
        "name": "2026 · Davet Test",
        "subject": "{{name}}, Makrobet'te seni 3.000 TL deneme kasası bekliyor!",
        "html_body": shell(
            title="Makrobet Deneme Bonusu",
            preheader="3.000 TL deneme kasası + numaralı promosyon listesi",
            body_rows=body,
        ),
        "text_body": (
            "Merhaba {{name}},\n\n"
            "3.000 TL deneme kasası seni bekliyor.\n"
            "1) %100 Kayıp Bonusu\n2) Arkadaşını Getir\n3) Race · Bilet · Manager\n\n"
            f"Katıl: {AFF}\n"
        ),
    }


def preset_davet_mailing() -> dict:
    items = [
        ("3.000 TL Deneme Kasası", "Yeni üye başlangıç kasası"),
        ("Arkadaşını Getir", "Arkadaşının yatırım bonusunu sen de al"),
        ("%100 Kayıp Bonusu", "Sıfır risk — güvence Makrobet’ten"),
        ("Amusnet Race · Bilet · Manager", "Yarış, bilet etkinliği, Makro Manager"),
        ("Prim & Çevrim Bonusu", "Aktif prim / çevrim kampanyaları"),
    ]
    body = (
        eyebrow("Özel davet")
        + headline("3.000 TL deneme kasası seni bekliyor")
        + hero_image(IMG_KASA, "Deneme Kasası")
        + cta_row("Hemen Kayıt Ol")
        + lead(
            "Merhaba <strong style='color:#ffffff;'>{{name}}</strong> — kayıt ol, deneme kasanı aç. "
            "Aşağıdaki kampanyalar da aktif."
        )
        + promo_cards(items, left_border=True)
        + tag_pills()
        + cta_row("Hemen Kayıt Ol")
    )
    return {
        "name": "2026 · Davet Mailingi",
        "subject": "{{name}}, Makrobet'te seni 3.000 TL deneme kasası bekliyor!",
        "html_body": shell(
            title="Makrobet Davet",
            preheader="Hazine kasası + Hemen Kayıt Ol",
            body_rows=body,
        ),
        "text_body": (
            "Merhaba {{name}},\n\n3.000 TL deneme kasası + promosyonlar.\n"
            f"Kayıt: {AFF}\n"
        ),
    }


def preset_pasif_uye() -> dict:
    items = [
        ("%100 Kayıp Bonusu", "Güvenli geri dönüş"),
        ("Makro Kasa", "Yatırıma ek kasa"),
        ("Amusnet Race", "Ödül havuzlu yarış"),
        ("Bilet · Makro Manager", "Etkinlik + rolling"),
        ("Prim & Çevrim", "Aktif dönem bonusları"),
    ]
    body = (
        eyebrow("Geri dönüş")
        + headline("Seni özledik — dönüş paketini aç")
        + hero_image(IMG_KAYIP, "Kayıp Bonusu")
        + cta_row("Hesabıma Dön")
        + lead(
            "Merhaba <strong style='color:#ffffff;'>{{name}}</strong> — %100 kayıp, kasa, race ve manager ile geri dön."
        )
        + promo_cards(items)
        + tag_pills()
        + cta_row("Hesabıma Dön")
    )
    return {
        "name": "2026 · Pasif Üye Geri Getirme",
        "subject": "{{name}}, hesabın seni bekliyor — kasa ve bonuslar hazır",
        "html_body": shell(
            title="Makrobet Geri Dönüş",
            preheader="Seni özledik — dönüş paketini aç",
            body_rows=body,
        ),
        "text_body": f"Merhaba {{{{name}}}},\n\nGeri dönüş paketleri hazır.\n{AFF}\n",
    }


def preset_memnuniyet() -> dict:
    items = [
        ("Memnuniyet Bonusu", "Özel jest — hesabını kontrol et"),
        ("%100 Kayıp Bonusu", "Risk Makrobet’te"),
        ("Makro Kasa", "Ek kasa fırsatı"),
        ("Prim · Çevrim · Manager · Bilet", "Aktif etkinlik seti"),
    ]
    body = (
        f"""
          <tr><td align="center" style="padding:4px 20px 8px;">{badge("MEMNUNİYET", solid=False)}</td></tr>
        """
        + headline("Senin için ekstra bir jest")
        + hero_image(IMG_KASA, "Makro Kasa")
        + cta_row("Bonusu Kontrol Et")
        + lead(
            "Merhaba <strong style='color:#ffffff;'>{{name}}</strong> — çekim aksamalarına özel memnuniyet jesti "
            "+ sitedeki güçlü kampanyalar."
        )
        + promo_cards(items)
        + tag_pills(("Memnuniyet", "Makro Kasa", "Prim", "Çevrim", "Manager", "Bilet"))
        + cta_row("Bonusu Kontrol Et")
    )
    return {
        "name": "2026 · Memnuniyet Bonusu",
        "subject": "{{name}}, senin için memnuniyet jesti hazır",
        "html_body": shell(
            title="Makrobet Memnuniyet",
            preheader="Senin için ekstra bir jest",
            body_rows=body,
        ),
        "text_body": f"Merhaba {{{{name}}}},\n\nMemnuniyet jesti hazır.\n{AFF}\n",
    }


def preset_ilk_yatirim() -> dict:
    items = [
        ("Makro Kasa", "Yatırıma ekstra kasa"),
        ("%100 Kayıp Güvencesi", "Rahat ilk adım"),
        ("Amusnet Race", "Ödül yarışı"),
        ("Prim · Çevrim · Bilet · Manager", "Tam paket"),
    ]
    body = (
        eyebrow("İlk yatırım")
        + headline("Kasanı büyütme zamanı")
        + hero_image(IMG_KASA, "Yatırım Kasası")
        + cta_row("İlk Yatırımı Yap")
        + lead(
            "Merhaba <strong style='color:#ffffff;'>{{name}}</strong> — ilk yatırımınla Makro Kasa, Race, prim ve çevrimi aç."
        )
        + promo_cards(items)
        + tag_pills()
        + cta_row("İlk Yatırımı Yap")
    )
    return {
        "name": "2026 · Yeni Üye İlk Yatırım",
        "subject": "{{name}}, ilk yatırımın için kasa paketleri",
        "html_body": shell(
            title="Makrobet İlk Yatırım",
            preheader="Kasanı büyütme zamanı",
            body_rows=body,
        ),
        "text_body": f"Merhaba {{{{name}}}},\n\nİlk yatırım paketleri.\n{AFF}\n",
    }


def preset_turnuva() -> dict:
    items = [
        ("Amusnet Race", "Ödül havuzlu yarış"),
        ("Bilet Etkinliği", "Bilet topla, ödül turuna gir"),
        ("Makro Manager", "Manager rolling"),
        ("Arkadaşını Getir", "Ekibini büyüt"),
    ]
    body = (
        eyebrow("Etkinlik")
        + headline("Race, Bilet, Manager bu hafta sahnede")
        + hero_image(IMG_RACE, "Amusnet Race")
        + cta_row("Etkinliklere Katıl")
        + lead(
            "Merhaba <strong style='color:#ffffff;'>{{name}}</strong> — turnuva ve toplu etkinliklere katıl."
        )
        + promo_cards(items)
        + tag_pills(("Amusnet Race", "Bilet", "Makro Manager", "Arkadaşını Getir", "Prim", "Çevrim"))
        + cta_row("Etkinliklere Katıl")
    )
    return {
        "name": "2026 · Turnuva & Bilet Etkinlikleri",
        "subject": "{{name}}, Race · Bilet · Makro Manager seni bekliyor",
        "html_body": shell(
            title="Makrobet Etkinlikler",
            preheader="Race, Bilet, Manager bu hafta sahnede",
            body_rows=body,
        ),
        "text_body": f"Merhaba {{{{name}}}},\n\nRace / Bilet / Manager.\n{AFF}\n",
    }


PRESET_BUILDERS = (
    preset_davet_test,
    preset_davet_mailing,
    preset_pasif_uye,
    preset_memnuniyet,
    preset_ilk_yatirim,
    preset_turnuva,
)


def build_all_presets() -> list[dict]:
    return [fn() for fn in PRESET_BUILDERS]
