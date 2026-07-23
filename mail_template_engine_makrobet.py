"""Makrobet unified HTML email template engine — 6 campaign presets.

Placeholders:
  __MAIL_LOGO__, __MB_IMG_KASA__, __MB_IMG_KAYIP__, __MB_IMG_ARKADAS__, __MB_IMG_RACE__
  {{name}}, {{link:sc:https://makrovip.com/Vipmail}}
"""

from __future__ import annotations

from typing import Sequence

# ── Design tokens ──────────────────────────────────────────────────────────
BG = "#08142c"
CARD = "#102244"
ROW = "#132a52"
TEXT = "#ffffff"
MUTED = "#94a3b8"
GOLD = "#ffcc00"
GOLD_SOFT_BG = "#1a1608"
BORDER = "#243b63"
INK = "#08142c"
CTA_INK = "#08142c"

FONT = "Arial, Helvetica, sans-serif"
MAX_W = 600

AFF = "https://makrovip.com/Vipmail"
CTA = "{{link:sc:https://makrovip.com/Vipmail}}"

LOGO = "__MAIL_LOGO__"
IMG_KASA = "__MB_IMG_KASA__"
IMG_KAYIP = "__MB_IMG_KAYIP__"
IMG_ARKADAS = "__MB_IMG_ARKADAS__"
IMG_RACE = "__MB_IMG_RACE__"


# ── Components ─────────────────────────────────────────────────────────────
def notice_spam() -> str:
    return f"""
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
    <tr>
      <td align="center" style="padding:0 12px 12px;">
        <table role="presentation" width="{MAX_W}" cellpadding="0" cellspacing="0" border="0"
          bgcolor="{GOLD_SOFT_BG}"
          style="width:100%;max-width:{MAX_W}px;background-color:{GOLD_SOFT_BG};
          border:1px solid #5a4208;border-radius:12px;">
          <tr>
            <td align="center" bgcolor="{GOLD_SOFT_BG}"
              style="padding:12px 16px;font-family:{FONT};font-size:12px;line-height:1.5;color:{GOLD};">
              Spam klasöründeyse <strong style="color:{GOLD};">butonlar çalışmaz</strong>.
              Önce <strong style="color:{GOLD};">Spam değil</strong> deyin, sonra tıklayın.
            </td>
          </tr>
        </table>
      </td>
    </tr>
  </table>"""


def logo_block(width: int = 180) -> str:
    """Exact-bg JPG logo — no plate mismatch vs email navy."""
    return (
        f'<a href="{CTA}" target="_blank" rel="noopener" style="text-decoration:none;border:0;">'
        f'<img src="{LOGO}" alt="Makrobet" width="{width}" border="0" '
        f'style="display:block;margin:0 auto;border:0;outline:none;'
        f'background-color:{BG};max-width:{width}px;width:{width}px;height:auto;"></a>'
    )


def badge(label: str, *, solid: bool = True) -> str:
    if solid:
        return (
            f'<span style="display:inline-block;background:{GOLD};color:{CTA_INK};'
            f"font-family:{FONT};font-size:11px;font-weight:800;letter-spacing:0.08em;"
            f'text-transform:uppercase;padding:6px 14px;border-radius:999px;">{label}</span>'
        )
    return (
        f'<span style="display:inline-block;background:{GOLD_SOFT_BG};color:{GOLD};'
        f"font-family:{FONT};font-size:11px;font-weight:800;letter-spacing:0.08em;"
        f"text-transform:uppercase;padding:6px 14px;border-radius:999px;"
        f'border:1px solid #5a4208;">{label}</span>'
    )


def cta_button(label: str) -> str:
    """Bulletproof table CTA — no MSO hacks that shift buttons."""
    return f"""
<table role="presentation" cellpadding="0" cellspacing="0" border="0" align="center" style="margin:0 auto;">
  <tr>
    <td align="center" bgcolor="{GOLD}" style="background-color:{GOLD};border-radius:12px;mso-padding-alt:14px 28px;">
      <a href="{CTA}" target="_blank" rel="noopener"
        style="display:inline-block;background-color:{GOLD};color:{CTA_INK};
        font-family:{FONT};font-size:15px;font-weight:800;line-height:1.2;
        text-decoration:none;padding:14px 28px;border-radius:12px;">{label}</a>
    </td>
  </tr>
</table>"""


def cta_row(label: str) -> str:
    return f"""
          <tr>
            <td align="center" style="padding:8px 20px 18px;">
              {cta_button(label)}
            </td>
          </tr>"""


def hero_image(src: str, alt: str, width: int = 300) -> str:
    return f"""
          <tr>
            <td align="center" bgcolor="{BG}" style="padding:2px 24px 10px;background-color:{BG};">
              <a href="{CTA}" target="_blank" rel="noopener" style="text-decoration:none;border:0;">
                <img src="{src}" alt="{alt}" width="{width}" border="0"
                  style="display:block;margin:0 auto;width:100%;max-width:{width}px;height:auto;
                  border:0;outline:none;background-color:{BG};">
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
            <td align="center" style="padding:0 20px 10px;font-family:{FONT};font-size:22px;
              line-height:1.3;font-weight:800;color:{TEXT};">{text}</td>
          </tr>"""


def lead(text: str) -> str:
    return f"""
          <tr>
            <td align="center" style="padding:0 22px 14px;font-family:{FONT};font-size:14px;
              line-height:1.55;color:{MUTED};">{text}</td>
          </tr>"""


def section_label(text: str) -> str:
    return f"""
          <tr>
            <td style="padding:2px 22px 10px;font-family:{FONT};font-size:11px;font-weight:800;
              letter-spacing:0.1em;text-transform:uppercase;color:{GOLD};">{text}</td>
          </tr>"""


def feature_box_3000() -> str:
    return f"""
          <tr>
            <td style="padding:4px 20px 14px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
                bgcolor="{CARD}" style="background-color:{CARD};border-radius:16px;border:2px solid {GOLD};">
                <tr>
                  <td align="center" style="padding:22px 16px;">
                    <div style="font-family:{FONT};font-size:11px;font-weight:800;color:{GOLD};
                      letter-spacing:0.12em;text-transform:uppercase;">★ Yeni üyelere özel ★</div>
                    <div style="font-family:{FONT};font-size:36px;font-weight:900;color:{GOLD};
                      line-height:1;margin-top:8px;">3.000 TL</div>
                    <div style="font-family:{FONT};font-size:16px;font-weight:800;color:{TEXT};
                      letter-spacing:0.04em;margin-top:6px;">DENEME KASASI</div>
                    <div style="font-family:{FONT};font-size:13px;line-height:1.5;color:{MUTED};
                      margin-top:10px;">Kayıt tamamlanınca deneme bakiyen hesabına tanımlanır.</div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>"""


def promo_card(title: str, desc: str) -> str:
    return f"""
          <tr>
            <td style="padding:0 20px 8px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
                bgcolor="{ROW}"
                style="background-color:{ROW};border:1px solid {BORDER};border-left:3px solid {GOLD};border-radius:12px;">
                <tr>
                  <td style="padding:13px 14px;">
                    <div style="font-family:{FONT};font-size:14px;font-weight:800;color:{GOLD};line-height:1.3;">{title}</div>
                    <div style="font-family:{FONT};font-size:12px;color:{MUTED};line-height:1.5;margin-top:5px;">{desc}</div>
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
                bgcolor="{ROW}"
                style="background-color:{ROW};border:1px solid {BORDER};border-left:3px solid {GOLD};border-radius:12px;">
                <tr>
                  <td width="40" valign="top" style="padding:13px 0 13px 12px;">
                    <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="26" height="26"
                      style="width:26px;height:26px;">
                      <tr>
                        <td align="center" valign="middle" bgcolor="{GOLD_SOFT_BG}"
                          style="width:26px;height:26px;background-color:{GOLD_SOFT_BG};border-radius:50%;
                          border:1px solid #5a4208;font-family:{FONT};font-size:12px;font-weight:800;color:{GOLD};">
                          {n}
                        </td>
                      </tr>
                    </table>
                  </td>
                  <td valign="top" style="padding:12px 14px 12px 6px;">
                    <div style="font-family:{FONT};font-size:13px;font-weight:800;color:{GOLD};line-height:1.3;">{title}</div>
                    <div style="font-family:{FONT};font-size:12px;color:{MUTED};margin-top:4px;line-height:1.5;">{desc}</div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>"""


def promo_cards(items: Sequence[tuple[str, str]]) -> str:
    return "".join(promo_card(t, d) for t, d in items)


def numbered_list(items: Sequence[tuple[str, str]]) -> str:
    return "".join(numbered_promo(i, t, d) for i, (t, d) in enumerate(items, 1))


def footer_legal() -> str:
    return f"""
          <tr>
            <td align="center" style="padding:12px 20px 22px;font-family:{FONT};font-size:11px;
              line-height:1.5;color:{MUTED};border-top:1px solid {BORDER};">
              Spam’de butonlar kilitli · Spam değil deyip tekrar dene<br>
              18+ · Sorumlu oyun · Makrobet
            </td>
          </tr>"""


def shell(*, title: str, body_rows: str, preheader: str = "") -> str:
    pre = (
        f'<div style="display:none;font-size:1px;line-height:1px;max-height:0;max-width:0;'
        f'opacity:0;overflow:hidden;mso-hide:all;">{preheader}&nbsp;&#847;&nbsp;&#847;</div>'
        if preheader
        else ""
    )
    return f"""<!DOCTYPE html>
<html lang="tr">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <meta http-equiv="X-UA-Compatible" content="IE=edge">
  <meta name="x-apple-disable-message-reformatting">
  <meta name="color-scheme" content="dark">
  <title>{title}</title>
  <!--[if mso]>
  <style>table,td{{font-family:Arial,sans-serif !important;}}</style>
  <![endif]-->
  <style type="text/css">
    body,table,td,a{{-webkit-text-size-adjust:100%;-ms-text-size-adjust:100%;}}
    table,td{{mso-table-lspace:0pt;mso-table-rspace:0pt;border-collapse:collapse;}}
    img{{-ms-interpolation-mode:bicubic;border:0;outline:none;text-decoration:none;display:block;}}
    body{{margin:0 !important;padding:0 !important;width:100% !important;background:{INK};}}
    a[x-apple-data-detectors]{{color:inherit !important;text-decoration:none !important;}}
    @media only screen and (max-width:620px){{
      .mb-shell{{width:100% !important;}}
    }}
  </style>
</head>
<body style="margin:0;padding:0;background-color:{INK};font-family:{FONT};">
  {pre}
  {notice_spam()}
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" bgcolor="{INK}" style="background-color:{INK};">
    <tr>
      <td align="center" style="padding:8px 10px 32px;">
        <table role="presentation" class="mb-shell" width="{MAX_W}" cellpadding="0" cellspacing="0" border="0"
          bgcolor="{BG}"
          style="width:100%;max-width:{MAX_W}px;background-color:{BG};border:1px solid {BORDER};border-radius:16px;">
          <tr><td height="3" bgcolor="{GOLD}" style="height:3px;line-height:3px;font-size:0;background-color:{GOLD};">&nbsp;</td></tr>
          <tr>
            <td align="center" bgcolor="{BG}" style="padding:22px 20px 12px;background-color:{BG};">
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


# ── Presets (coherent copy, no tag pills, single bottom CTA) ───────────────
def preset_davet_test() -> dict:
    items = [
        (
            "%100 Kayıp Bonusu",
            "Yatırımın kayba dönerse aynı tutarı tekrar hesabına ekleriz — risk Makrobet’te.",
        ),
        (
            "Arkadaşını Getir",
            "Davet ettiğin üye ilk yatırımını yapınca hem sen hem o bonus kazanır.",
        ),
        (
            "Amusnet Race",
            "Haftalık yarış sıralamasına gir; ödül havuzundan payını kap.",
        ),
    ]
    body = (
        f'<tr><td align="center" style="padding:4px 20px 10px;">{badge("DENEME BONUSU")}</td></tr>'
        + eyebrow("Özel davet")
        + headline("Merhaba {{name}}, seni 3.000 TL deneme kasası bekliyor")
        + lead("Kayıt ol, deneme kasanı aç. Aşağıdaki 3 kampanya da yeni üyelerde aktif.")
        + feature_box_3000()
        + section_label("Diğer promosyonlar")
        + numbered_list(items)
        + cta_row("Deneme Bonusu Al")
    )
    return {
        "name": "2026 · Davet Test",
        "subject": "{{name}}, Makrobet'te seni 3.000 TL deneme kasası bekliyor!",
        "html_body": shell(
            title="Makrobet Deneme Bonusu",
            preheader="3.000 TL deneme kasası seni bekliyor",
            body_rows=body,
        ),
        "text_body": (
            "Merhaba {{name}},\n\n"
            "3.000 TL deneme kasası seni bekliyor.\n"
            "1) %100 Kayıp Bonusu\n2) Arkadaşını Getir\n3) Amusnet Race\n\n"
            f"Katıl: {AFF}\n"
        ),
    }


def preset_davet_mailing() -> dict:
    items = [
        (
            "3.000 TL Deneme Kasası",
            "Yeni üyelikte hesabına tanımlanan başlangıç bakiyesi — kayıt sonrası hemen oyna.",
        ),
        (
            "Arkadaşını Getir",
            "Arkadaşın yatırım yaptıkça sen de bonus al; davet linkinle ekibini büyüt.",
        ),
        (
            "%100 Kayıp Bonusu",
            "Kaybın kadar ek bakiye tanımlanır; ilk adımlarını güvenceye alırsın.",
        ),
        (
            "Amusnet Race",
            "Ödül havuzlu slot yarışında sıralamaya gir, haftalık ödülleri kovala.",
        ),
        (
            "Prim & Çevrim",
            "Güncel prim ve çevrim kampanyalarıyla yatırımını daha verimli kullan.",
        ),
    ]
    body = (
        eyebrow("Özel davet")
        + headline("3.000 TL deneme kasası seni bekliyor")
        + hero_image(IMG_KASA, "Deneme Kasası")
        + lead(
            "Merhaba <strong style='color:#ffffff;'>{{name}}</strong> — kayıt ol, deneme kasanı aç. "
            "Aynı anda aktif olan kampanyalar:"
        )
        + promo_cards(items)
        + cta_row("Hemen Kayıt Ol")
    )
    return {
        "name": "2026 · Davet Mailingi",
        "subject": "{{name}}, Makrobet'te seni 3.000 TL deneme kasası bekliyor!",
        "html_body": shell(
            title="Makrobet Davet",
            preheader="3.000 TL deneme kasası + Hemen Kayıt Ol",
            body_rows=body,
        ),
        "text_body": f"Merhaba {{{{name}}}},\n\n3.000 TL deneme kasası seni bekliyor.\n{AFF}\n",
    }


def preset_pasif_uye() -> dict:
    items = [
        (
            "%100 Kayıp Bonusu",
            "Geri döndüğünde kayıpların kadar ek bakiye — yeniden başlamak için güvence.",
        ),
        (
            "Makro Kasa",
            "Yatırımına ek kasa tanımı; dönüş yatırımını daha güçlü başlat.",
        ),
        (
            "Amusnet Race",
            "Yarışa tekrar katıl, sıralamada yüksel, ödül havuzundan pay al.",
        ),
        (
            "Bilet Etkinliği",
            "Etkinlik biletlerini topla; çekiliş ve ödül turlarına hak kazan.",
        ),
        (
            "Makro Manager",
            "Manager döneminde rolling hedeflerini tamamla, ekstra prim kap.",
        ),
    ]
    body = (
        eyebrow("Geri dönüş")
        + headline("Seni özledik — dönüş paketini aç")
        + hero_image(IMG_KAYIP, "Kayıp Bonusu")
        + lead(
            "Merhaba <strong style='color:#ffffff;'>{{name}}</strong> — hesabın seni bekliyor. "
            "Dönüş paketindeki kampanyalar:"
        )
        + promo_cards(items)
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
        (
            "Memnuniyet Bonusu",
            "Çekim veya işlem aksamalarına özel jest — hesabındaki tanımlı bakiyeyi kontrol et.",
        ),
        (
            "%100 Kayıp Bonusu",
            "Yeniden yatırımında kayıp kadar ek bakiye; deneyimini telafi edelim.",
        ),
        (
            "Makro Kasa",
            "Memnuniyet paketinin yanında yatırıma ek kasa fırsatı.",
        ),
        (
            "Prim & Çevrim",
            "Aktif prim / çevrim kampanyalarıyla bakiyeni daha verimli kullan.",
        ),
    ]
    body = (
        f'<tr><td align="center" style="padding:4px 20px 8px;">{badge("MEMNUNİYET", solid=False)}</td></tr>'
        + headline("Senin için ekstra bir jest")
        + hero_image(IMG_KASA, "Memnuniyet")
        + lead(
            "Merhaba <strong style='color:#ffffff;'>{{name}}</strong> — yaşanan aksaklığa özel "
            "memnuniyet jesti ve destek kampanyaları:"
        )
        + promo_cards(items)
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
        (
            "Makro Kasa",
            "İlk yatırımına ekstra kasa eklenir — bakiyen ilk günden büyür.",
        ),
        (
            "%100 Kayıp Güvencesi",
            "İlk yatırımın kayba dönerse aynı tutarı tekrar tanımlarız.",
        ),
        (
            "Amusnet Race",
            "İlk yatırımdan sonra yarışa katıl; ödül sıralamasında yerini al.",
        ),
        (
            "Prim & Çevrim",
            "Yeni üye prim / çevrim kampanyalarıyla ilk yatırımını değerlendir.",
        ),
    ]
    body = (
        eyebrow("İlk yatırım")
        + headline("Kasanı büyütme zamanı")
        + hero_image(IMG_KASA, "Yatırım Kasası")
        + lead(
            "Merhaba <strong style='color:#ffffff;'>{{name}}</strong> — ilk yatırımınla "
            "aşağıdaki paketleri aç:"
        )
        + promo_cards(items)
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
        (
            "Amusnet Race",
            "Ödül havuzlu slot yarışı — sıralamaya gir, haftanın ödüllerini kap.",
        ),
        (
            "Bilet Etkinliği",
            "Oynadıkça bilet biriktir; çekiliş ve özel ödül turlarına katıl.",
        ),
        (
            "Makro Manager",
            "Manager döneminde hedef rolling’i tamamla, ekstra prim kazan.",
        ),
        (
            "Arkadaşını Getir",
            "Ekibini davet et; arkadaşın yatırım yaptıkça sen de bonus al.",
        ),
    ]
    body = (
        eyebrow("Etkinlik")
        + headline("Race, Bilet, Manager bu hafta sahnede")
        + hero_image(IMG_RACE, "Amusnet Race")
        + lead(
            "Merhaba <strong style='color:#ffffff;'>{{name}}</strong> — bu haftanın "
            "turnuva ve etkinlikleri:"
        )
        + promo_cards(items)
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
