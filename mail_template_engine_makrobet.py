"""Makrobet unified HTML email template engine — 9 campaign presets.

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
    btn = (
        f'<a href="__NOT_SPAM_URL__" data-mm-not-spam="1" target="_blank" rel="noopener" '
        f'style="color:{INK};background:{GOLD};font-weight:700;text-decoration:none;'
        f'padding:6px 12px;border-radius:8px;display:inline-block;margin-top:8px;">'
        f"Spam değil olarak işaretledim</a>"
    )
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
              Önce Gmail/Outlook’ta <strong style="color:{GOLD};">Spam değil</strong> deyin, sonra buraya basın:<br>
              {btn}
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


def badge(label: str, *, solid: bool = True, glow: bool = False) -> str:
    glow_css = (
        f"box-shadow:0 0 0 3px rgba(255,204,0,0.22),0 0 18px rgba(255,204,0,0.45);"
        if glow
        else ""
    )
    if solid:
        return (
            f'<span style="display:inline-block;background:{GOLD};color:{CTA_INK};'
            f"font-family:{FONT};font-size:11px;font-weight:800;letter-spacing:0.1em;"
            f"text-transform:uppercase;padding:8px 18px;border-radius:999px;{glow_css}"
            f'">{label}</span>'
        )
    return (
        f'<span style="display:inline-block;background:{GOLD_SOFT_BG};color:{GOLD};'
        f"font-family:{FONT};font-size:11px;font-weight:800;letter-spacing:0.1em;"
        f"text-transform:uppercase;padding:8px 18px;border-radius:999px;"
        f'border:1px solid #5a4208;{glow_css}">{label}</span>'
    )


def cta_button(
    label: str,
    *,
    wide: bool = False,
    glow: bool = False,
    gradient: bool = False,
    font_px: int = 15,
    pad: str = "14px 28px",
    width_pct: int | None = None,
) -> str:
    """İç buton — HTML width=\"100%\" KULLANMA (padding’li hücrede sağa taşar)."""
    bg = "linear-gradient(180deg,#ffe066 0%,#ffcc00 45%,#e6b800 100%)" if gradient else GOLD
    bg_solid = GOLD
    shadow = (
        "box-shadow:0 0 0 2px rgba(255,204,0,0.35),0 8px 24px rgba(255,204,0,0.35);"
        if glow
        else ""
    )
    link = (
        f'<a href="{CTA}" target="_blank" rel="noopener" '
        f'style="display:block;box-sizing:border-box;background-color:{bg_solid};background:{bg};'
        f"color:{CTA_INK};font-family:{FONT};font-size:{font_px}px;font-weight:800;"
        f'line-height:1.2;text-decoration:none;padding:{pad};border-radius:12px;text-align:center;">'
        f"{label}</a>"
    )
    cell = (
        f'<td align="center" bgcolor="{bg_solid}" '
        f'style="background-color:{bg_solid};background:{bg};border-radius:12px;'
        f'mso-padding-alt:{pad};{shadow}">{link}</td>'
    )
    if width_pct is not None:
        return f"""
<table role="presentation" cellpadding="0" cellspacing="0" border="0" align="center"
  style="margin:0 auto;width:{int(width_pct)}%;max-width:{int(width_pct)}%;border-collapse:collapse;">
  <tr>{cell}</tr>
</table>"""
    if wide:
        # Kartlarla aynı: dış 20px padding cta_row’da; burada sadece içerik genişliği
        return f"""
<table role="presentation" cellpadding="0" cellspacing="0" border="0"
  style="width:100%;max-width:100%;border-collapse:collapse;">
  <tr>{cell}</tr>
</table>"""
    return f"""
<table role="presentation" cellpadding="0" cellspacing="0" border="0" align="center"
  style="margin:0 auto;border-collapse:collapse;">
  <tr>{cell}</tr>
</table>"""


def cta_row(
    label: str,
    *,
    wide: bool = False,
    glow: bool = False,
    gradient: bool = False,
    font_px: int = 15,
    pad: str = "14px 28px",
    width_pct: int | None = None,
) -> str:
    """Kartlarla aynı dış gutter: padding 10px 20px 20px — taşma yok."""
    btn = cta_button(
        label,
        wide=wide,
        glow=glow,
        gradient=gradient,
        font_px=font_px,
        pad=pad,
        width_pct=width_pct,
    )
    return f"""
          <tr>
            <td align="left" style="padding:10px 20px 20px;">
              {btn}
            </td>
          </tr>"""
def hero_image(src: str, alt: str, width: int = 300, *, soft: bool = False, glow: bool = False) -> str:
    radius = "18px" if soft else "0"
    shadow = (
        "box-shadow:0 0 28px rgba(255,204,0,0.35),0 0 0 1px rgba(255,204,0,0.2);"
        if glow
        else ""
    )
    return f"""
          <tr>
            <td align="center" bgcolor="{BG}" style="padding:4px 24px 12px;background-color:{BG};">
              <a href="{CTA}" target="_blank" rel="noopener" style="text-decoration:none;border:0;">
                <img src="{src}" alt="{alt}" width="{width}" border="0"
                  style="display:block;margin:0 auto;width:100%;max-width:{width}px;height:auto;
                  border:0;outline:none;background-color:transparent;border-radius:{radius};{shadow}">
              </a>
            </td>
          </tr>"""


def gold_subhead(text: str) -> str:
    return f"""
          <tr>
            <td align="center" style="padding:0 22px 14px;font-family:{FONT};font-size:16px;
              line-height:1.4;font-weight:800;color:{GOLD};">{text}</td>
          </tr>"""


def eyebrow(text: str) -> str:
    return f"""
          <tr>
            <td align="center" style="padding:0 20px 6px;font-family:{FONT};font-size:11px;
              font-weight:800;letter-spacing:0.14em;text-transform:uppercase;color:{GOLD};">{text}</td>
          </tr>"""


def headline(text: str, *, size: int = 22, color: str | None = None) -> str:
    c = color or TEXT
    return f"""
          <tr>
            <td align="center" style="padding:0 20px 10px;font-family:{FONT};font-size:{size}px;
              line-height:1.3;font-weight:800;color:{c};">{text}</td>
          </tr>"""


def lead(text: str, *, size: int = 14, emphasize: bool = False) -> str:
    color = TEXT if emphasize else MUTED
    weight = "700" if emphasize else "400"
    return f"""
          <tr>
            <td align="center" style="padding:0 22px 14px;font-family:{FONT};font-size:{size}px;
              line-height:1.55;font-weight:{weight};color:{color};">{text}</td>
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


def feature_box(
    *,
    kicker: str,
    big: str,
    subtitle: str,
    note: str,
) -> str:
    return f"""
          <tr>
            <td style="padding:4px 20px 14px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
                bgcolor="{CARD}" style="background-color:{CARD};border-radius:16px;border:2px solid {GOLD};">
                <tr>
                  <td align="center" style="padding:22px 16px;">
                    <div style="font-family:{FONT};font-size:11px;font-weight:800;color:{GOLD};
                      letter-spacing:0.12em;text-transform:uppercase;">{kicker}</div>
                    <div style="font-family:{FONT};font-size:30px;font-weight:900;color:{GOLD};
                      line-height:1.1;margin-top:8px;">{big}</div>
                    <div style="font-family:{FONT};font-size:15px;font-weight:800;color:{TEXT};
                      letter-spacing:0.03em;margin-top:8px;">{subtitle}</div>
                    <div style="font-family:{FONT};font-size:13px;line-height:1.55;color:{MUTED};
                      margin-top:10px;">{note}</div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>"""


def promo_card(
    title: str,
    desc: str,
    *,
    highlight: bool = False,
    icon: str | None = None,
    pad_y: int = 12,
) -> str:
    # Hepsi aynı dış hiza (20px) + aynı sol altın şerit — highlight sadece arka plan
    border = f"border:1px solid {BORDER};border-left:5px solid {GOLD};"
    bg = CARD if highlight else ROW
    icon_cell = ""
    if icon:
        icon_cell = f"""
                  <td width="44" valign="middle" style="padding:{pad_y}px 0 {pad_y}px 12px;">
                    <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="32" height="32">
                      <tr>
                        <td align="center" valign="middle" bgcolor="{GOLD_SOFT_BG}"
                          style="width:32px;height:32px;background-color:{GOLD_SOFT_BG};border-radius:8px;
                          border:1px solid #5a4208;font-family:{FONT};font-size:14px;line-height:1;">{icon}</td>
                      </tr>
                    </table>
                  </td>"""
    return f"""
          <tr>
            <td align="left" style="padding:0 20px 10px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
                bgcolor="{bg}"
                style="width:100%;background-color:{bg};{border}border-radius:12px;">
                <tr>
                  {icon_cell}
                  <td style="padding:{pad_y}px 14px;">
                    <div style="font-family:{FONT};font-size:14px;font-weight:800;color:{GOLD};line-height:1.3;">{title}</div>
                    <div style="font-family:{FONT};font-size:12px;color:{MUTED};line-height:1.55;margin-top:6px;">{desc}</div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>"""


def numbered_promo(n: int, title: str, desc: str) -> str:
    return f"""
          <tr>
            <td style="padding:0 20px 10px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
                bgcolor="{ROW}"
                style="background-color:{ROW};border:1px solid {BORDER};border-left:5px solid {GOLD};border-radius:12px;">
                <tr>
                  <td width="48" valign="middle" align="center" style="padding:14px 0 14px 12px;">
                    <table role="presentation" cellpadding="0" cellspacing="0" border="0" width="30" height="30"
                      style="width:30px;height:30px;margin:0 auto;">
                      <tr>
                        <td align="center" valign="middle" bgcolor="{GOLD}"
                          style="width:30px;height:30px;background-color:{GOLD};border-radius:50%;
                          font-family:{FONT};font-size:13px;font-weight:900;color:{CTA_INK};line-height:30px;">
                          {n}
                        </td>
                      </tr>
                    </table>
                  </td>
                  <td valign="middle" style="padding:14px 14px 14px 8px;">
                    <div style="font-family:{FONT};font-size:14px;font-weight:800;color:{GOLD};line-height:1.3;">{title}</div>
                    <div style="font-family:{FONT};font-size:12px;color:{MUTED};margin-top:5px;line-height:1.55;">{desc}</div>
                  </td>
                </tr>
              </table>
            </td>
          </tr>"""


def promo_cards(
    items: Sequence[tuple[str, str]],
    *,
    highlight_first: int = 0,
    icons: Sequence[str] | None = None,
    pad_y: int = 12,
) -> str:
    out = []
    for i, (t, d) in enumerate(items):
        icon = icons[i] if icons and i < len(icons) else None
        out.append(
            promo_card(
                t,
                d,
                highlight=(i < highlight_first),
                icon=icon,
                pad_y=pad_y,
            )
        )
    return "".join(out)


def numbered_list(items: Sequence[tuple[str, str]]) -> str:
    return "".join(numbered_promo(i, t, d) for i, (t, d) in enumerate(items, 1))


def dual_feature_cards(left: tuple[str, str], right: tuple[str, str]) -> str:
    """İki kart — tek sütun (aynı dış hiza; yan yana mobilde yamuk görünüyordu)."""
    return promo_cards([left, right], highlight_first=2, pad_y=14)


def footer_legal() -> str:
    """Dipnot — spam uyarısı üstte (notice_spam); burada sadece yasal."""
    return f"""
          <tr>
            <td align="center" style="padding:14px 20px 22px;font-family:{FONT};font-size:11px;
              line-height:1.55;color:{MUTED};border-top:1px solid {BORDER};">
              18+ · Sorumlu oyun · Makrobet<br>
              <a href="{CTA}" target="_blank" rel="noopener"
                style="color:{GOLD};font-weight:700;text-decoration:none;">makrovip.com/Vipmail</a>
            </td>
          </tr>"""


# ── Sterile (Betroz-style) layout — navy + gold, no promo images ───────────
ACCENT_TEAL = "#2dd4bf"
ACCENT_GREEN = "#4ade80"
ACCENT_BLUE = "#60a5fa"
ACCENT_VIOLET = "#a78bfa"
STERILE_CARD = "#0c1a36"
STERILE_HERO = "#0a1834"


def _sterile_login_pill(label: str = "GİRİŞ YAP") -> str:
    return (
        f'<a href="{CTA}" target="_blank" rel="noopener" '
        f'style="display:inline-block;background-color:{GOLD};color:{CTA_INK};'
        f"font-family:{FONT};font-size:12px;font-weight:800;letter-spacing:0.06em;"
        f'text-decoration:none;padding:10px 18px;border-radius:999px;">{label}</a>'
    )


def _sterile_header() -> str:
    return f"""
          <tr>
            <td style="padding:18px 20px 8px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td align="left" valign="middle" style="padding:0;">
                    <a href="{CTA}" target="_blank" rel="noopener" style="text-decoration:none;border:0;">
                      <img src="{LOGO}" alt="Makrobet" width="148" border="0"
                        style="display:block;border:0;outline:none;background-color:{BG};
                        max-width:148px;width:148px;height:auto;">
                    </a>
                  </td>
                  <td align="right" valign="middle" style="padding:0;">
                    {_sterile_login_pill()}
                  </td>
                </tr>
              </table>
            </td>
          </tr>"""


def _sterile_tag(text: str) -> str:
    return f"""
          <tr>
            <td align="center" style="padding:10px 20px 12px;">
              <span style="display:inline-block;border:1px solid {GOLD};color:{GOLD};
                font-family:{FONT};font-size:11px;font-weight:800;letter-spacing:0.12em;
                text-transform:uppercase;padding:7px 14px;border-radius:8px;">{text}</span>
            </td>
          </tr>"""


def _sterile_stat(label: str, color: str) -> str:
    return f"""
                  <td width="33%" align="center" valign="top" style="padding:6px 4px;">
                    <div style="font-family:{FONT};font-size:11px;font-weight:800;letter-spacing:0.04em;
                      text-transform:uppercase;color:{color};line-height:1.35;">{label}</div>
                  </td>"""


def _sterile_glow_card(
    title: str,
    subtitle: str,
    accent: str,
    *,
    tag: str | None = None,
    pad: str = "18px 16px",
) -> str:
    tag_html = ""
    if tag:
        tag_html = (
            f'<div style="font-family:{FONT};font-size:10px;font-weight:800;letter-spacing:0.1em;'
            f'text-transform:uppercase;color:{accent};margin-bottom:8px;">{tag}</div>'
        )
    return f"""
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0"
                bgcolor="{STERILE_CARD}"
                style="width:100%;background-color:{STERILE_CARD};border:1px solid {accent};
                border-radius:14px;box-shadow:0 0 0 1px rgba(255,204,0,0.04),0 0 18px rgba(0,0,0,0.35);">
                <tr>
                  <td style="padding:{pad};">
                    <div style="width:36px;height:3px;background-color:{accent};border-radius:2px;
                      font-size:0;line-height:0;margin-bottom:12px;">&nbsp;</div>
                    {tag_html}
                    <div style="font-family:{FONT};font-size:15px;font-weight:800;color:{TEXT};
                      line-height:1.35;letter-spacing:0.02em;">{title}</div>
                    <div style="font-family:{FONT};font-size:12px;font-weight:600;color:{MUTED};
                      line-height:1.5;margin-top:8px;">{subtitle}</div>
                  </td>
                </tr>
              </table>"""


def _sterile_two_col(left_html: str, right_html: str) -> str:
    return f"""
          <tr>
            <td style="padding:0 16px 10px;">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td width="50%" valign="top" style="padding:0 5px 0 0;">{left_html}</td>
                  <td width="50%" valign="top" style="padding:0 0 0 5px;">{right_html}</td>
                </tr>
              </table>
            </td>
          </tr>"""


def shell_sterile(*, title: str, body_rows: str, preheader: str = "") -> str:
    """Logo + GİRİŞ YAP header; görselsiz steril kart grid."""
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
      .mb-stack{{display:block !important;width:100% !important;}}
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
          style="width:100%;max-width:{MAX_W}px;background-color:{BG};border:1px solid {BORDER};border-radius:18px;">
          {_sterile_header()}
          {body_rows}
          {footer_legal()}
        </table>
      </td>
    </tr>
  </table>
</body>
</html>"""


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
def preset_davet_deneme_kayip() -> dict:
    """Davet mailing — 3.000 TL deneme kasası + %100 kayıp (promosyonlar sayfası)."""
    body = (
        f'<tr><td align="center" style="padding:6px 20px 10px;">{badge("ÖZEL DAVET", glow=True)}</td></tr>'
        + eyebrow("Makrobet’e özel giriş")
        + headline("Merhaba {{name}}, seni 3.000 TL deneme kasası bekliyor", size=24)
        + lead(
            "Kayıt ol, deneme bakiyeni aç. İlk yatırımında da "
            "<strong style=\"color:#ffcc00;\">%100 kayıp güvencesi</strong> yanında.",
            size=15,
            emphasize=True,
        )
        + feature_box_3000()
        + hero_image(IMG_KAYIP, "%100 Kayıp Bonusu", soft=True, glow=True)
        + feature_box(
            kicker="★ Sıfır risk ★",
            big="%100",
            subtitle="KAYIP BONUSU",
            note="Yatırım senden, güvence Makrobet’ten — kaybın kadar bakiye yeniden tanımlanır.",
        )
        + section_label("Neden şimdi?")
        + promo_cards(
            [
                (
                    "3.000 TL Deneme Kasası",
                    "Yeni üyelikte başlangıç bakiyen hesabına tanımlanır; hemen oynamaya başla.",
                ),
                (
                    "%100 Kayıp Bonusu",
                    "İlk adımlarını güvenceye al — yatırımın kayba dönerse aynı tutar geri gelir.",
                ),
                (
                    "VIP Club & Güncel Promosyonlar",
                    "Kayıt sonrası Gün Sonu Kasası, Makro Görev ve VIP avantajları da açılır.",
                ),
            ],
            pad_y=12,
        )
        + cta_row("Daveti Aç · Hemen Kayıt Ol", wide=True, font_px=16, pad="16px 36px", glow=True)
    )
    return {
        "name": "2026 · Davet · Deneme + %100 Kayıp",
        "subject": "{{name}}, 3.000 TL deneme kasası + %100 kayıp güvencesi seni bekliyor",
        "html_body": shell(
            title="Makrobet Özel Davet",
            preheader="3.000 TL deneme kasası · %100 kayıp bonusu · Hemen kayıt ol",
            body_rows=body,
        ),
        "text_body": (
            "Merhaba {{name}},\n\n"
            "Makrobet özel davet:\n"
            "• 3.000 TL deneme kasası — kayıt sonrası hesabına tanımlanır\n"
            "• %100 kayıp bonusu — yatırım senden, güvence Makrobet’ten\n\n"
            f"Hemen kayıt ol: {AFF}\n"
        ),
    }


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
        f'<tr><td align="center" style="padding:6px 20px 12px;">{badge("ÖZEL DAVET", glow=True)}</td></tr>'
        + eyebrow("Deneme bonusu")
        + headline("Merhaba {{name}}, seni 3.000 TL deneme kasası bekliyor", size=24)
        + lead("Kayıt ol, deneme kasanı aç. Aşağıdaki 3 kampanya da yeni üyelerde aktif.")
        + feature_box_3000()
        + section_label("Diğer promosyonlar")
        + numbered_list(items)
        + cta_row("Deneme Bonusu Al", wide=True, font_px=16, pad="16px 36px")
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
        f'<tr><td align="center" style="padding:4px 20px 10px;">{badge("ÖZEL DAVET", glow=True)}</td></tr>'
        + headline("3.000 TL deneme kasası seni bekliyor", size=24)
        + hero_image(IMG_KASA, "Deneme Kasası", soft=True, glow=True)
        + lead(
            "Merhaba <strong style=\"color:#ffcc00;\">{{name}}</strong> — kayıt ol, deneme kasanı aç.",
            size=17,
            emphasize=True,
        )
        + lead("Aynı anda aktif olan kampanyalar:")
        + promo_cards(items, pad_y=12)
        + cta_row("Hemen Kayıt Ol", wide=True, font_px=16, pad="16px 36px")
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
    featured = [
        (
            "Makro Kasa",
            "Yatırımına ek kasa tanımı; dönüş yatırımını daha güçlü başlat.",
        ),
        (
            "%100 Kayıp Bonusu",
            "Geri döndüğünde kayıpların kadar ek bakiye — yeniden başlamak için güvence.",
        ),
    ]
    rest = [
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
        f'<tr><td align="center" style="padding:4px 20px 8px;">{badge("ÖZEL TEKLİF", glow=True)}</td></tr>'
        + eyebrow("Geri dönüş")
        + headline("Seni özledik — dönüş paketini aç", size=24)
        + hero_image(IMG_KAYIP, "Kayıp Bonusu", soft=True, glow=True)
        + gold_subhead("Hesabına ekstra bakiye tanımlandı!")
        + lead(
            "Merhaba <strong style='color:#ffffff;'>{{name}}</strong> — hesabın seni bekliyor. "
            "Dönüş paketindeki kampanyalar:",
            size=15,
        )
        + section_label("Öne çıkanlar")
        + promo_cards(featured, highlight_first=2, pad_y=14)
        + section_label("Ayrıca seni bekleyenler")
        + promo_cards(rest, pad_y=12)
        + cta_row("Hesabıma Dön", glow=True, font_px=16, pad="16px 36px", wide=True)
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
    # Logo shell’de zorunlu; VIP rozet + hero ile üst alan güçlendirilir
    body = (
        f'<tr><td align="center" style="padding:6px 20px 10px;">{badge("MEMNUNİYET", glow=True)}</td></tr>'
        + f"""
          <tr>
            <td align="center" style="padding:0 20px 8px;">
              <table role="presentation" cellpadding="0" cellspacing="0" border="0" align="center">
                <tr>
                  <td align="center" bgcolor="{GOLD_SOFT_BG}"
                    style="background-color:{GOLD_SOFT_BG};border:1px solid #5a4208;border-radius:14px;
                    padding:10px 18px;font-family:{FONT};font-size:13px;font-weight:800;color:{GOLD};">
                    ★ VIP jest · hesabına özel
                  </td>
                </tr>
              </table>
            </td>
          </tr>"""
        + headline("Senin için ekstra bir jest", size=20)
        + hero_image(IMG_KASA, "Memnuniyet", soft=True, glow=True)
        + lead(
            "Merhaba <strong style='color:#ffffff;'>{{name}}</strong> — yaşanan aksaklığa özel "
            "memnuniyet jesti ve destek kampanyaları:",
            size=15,
        )
        + promo_cards(items, highlight_first=2, pad_y=14)
        + cta_row(
            "Bonusunu Kontrol Et",
            width_pct=80,
            font_px=16,
            pad="16px 28px",
        )
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
        + headline("Kasanı büyütme zamanı", size=26, color=GOLD)
        + hero_image(IMG_KASA, "Yatırım Kasası", soft=True, glow=True)
        + lead(
            "Merhaba <strong style='color:#ffffff;'>{{name}}</strong> — ilk yatırımınla "
            "aşağıdaki paketleri aç:",
            size=15,
        )
        # Tek sütun, aynı 20px dış hiza — yan yana kartlar mobilde yamuk görünüyordu
        + promo_cards(items, highlight_first=2, pad_y=14)
        + cta_row(
            "İlk Yatırımı Yap",
            gradient=True,
            wide=True,
            font_px=16,
            pad="16px 36px",
        )
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
    icons = ("🏆", "🎟", "📊", "🤝")
    body = (
        f'<tr><td align="center" style="padding:4px 20px 8px;">{badge("BU HAFTA", glow=True)}</td></tr>'
        + eyebrow("Etkinlik")
        + headline("Race, Bilet, Manager — bu hafta sahne senin!", size=24)
        + hero_image(IMG_RACE, "Amusnet Race", soft=True, glow=True)
        + lead(
            "Merhaba <strong style='color:#ffffff;'>{{name}}</strong> — bu haftanın "
            "turnuva ve etkinlikleri:",
            size=15,
        )
        + promo_cards(items, icons=icons, pad_y=13)
        + cta_row("Etkinliklere Katıl", pad="14px 32px", font_px=16, wide=True)
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


def preset_yil_donumu() -> dict:
    """Kayıt tarihinden itibaren yıl dönümü → hesaba ödül tanımı."""
    steps = [
        (
            "Kayıt tarihin baz alınır",
            "Üyelik yıl dönümün, hesabına ilk kayıt olduğun güne göre hesaplanır.",
        ),
        (
            "Ödül otomatik eklenir",
            "Yıl dönümünde özel kutlama ödülü hesabına tanımlanır — ekstra başvuru gerekmez.",
        ),
        (
            "Hesabından kontrol et",
            "Bakiyeni / bonus alanını aç; ödülün yansıdığını gör ve oynamaya devam et.",
        ),
    ]
    extras = [
        (
            "Sadakat jesti",
            "Her yıl dönümünde Makrobet ailesine katıldığın günü birlikte kutlarız.",
        ),
        (
            "Aktif kampanyalar",
            "Ödülünün yanında Race, Bilet ve Manager etkinlikleri de seni bekliyor.",
        ),
    ]
    body = (
        f'<tr><td align="center" style="padding:4px 20px 8px;">{badge("YIL DÖNÜMÜ")}</td></tr>'
        + eyebrow("Kutlama")
        + headline("Kayıt yıl dönümün kutlu olsun, {{name}}")
        + hero_image(IMG_KASA, "Yıl Dönümü Ödülü")
        + lead(
            "Hesabının <strong style='color:#ffffff;'>kayıt tarihinden itibaren</strong> her yıl "
            "dönümünde özel bir kutlama ödülü hesabına ekleniyor. Bu mail, o jesti haber vermek için."
        )
        + feature_box(
            kicker="★ Üyelik yıl dönümü ★",
            big="ÖDÜL HESABINDA",
            subtitle="Kayıt günün anısına tanımlanır",
            note="Tarih geldiğinde ödül bakiyene / bonus alanına işlenir. Detay için hesabına bak.",
        )
        + section_label("Nasıl işler?")
        + numbered_list(steps)
        + section_label("Birlikte devam")
        + promo_cards(extras)
        + cta_row("Ödülümü Kontrol Et")
    )
    return {
        "name": "2026 · Yıl Dönümü Kutlaması",
        "subject": "{{name}}, kayıt yıl dönümün kutlu olsun — ödülün hesabında!",
        "html_body": shell(
            title="Makrobet Yıl Dönümü",
            preheader="Kayıt yıl dönümü ödülün hesabına eklendi",
            body_rows=body,
        ),
        "text_body": (
            "Merhaba {{name}},\n\n"
            "Kayıt yıl dönümün kutlu olsun!\n"
            "Hesabının kayıt tarihinden itibaren her yıl dönümünde özel ödül hesabına eklenir.\n"
            "1) Kayıt tarihin baz alınır\n"
            "2) Ödül otomatik eklenir\n"
            "3) Hesabından kontrol et\n\n"
            f"Hesaba git: {AFF}\n"
        ),
    }


def preset_dogum_gunu() -> dict:
    """Doğum günü kutlaması — hediye hesabına eklendi."""
    steps = [
        (
            "Doğum günün kutlu olsun",
            "Bugün senin günün — Makrobet ailesi adına en güzel dileklerimizle.",
        ),
        (
            "Hediye hesabında",
            "Doğum günü hediyen hesabına tanımlandı; ekstra başvuru veya kod gerekmez.",
        ),
        (
            "Hemen kontrol et",
            "Bakiyeni / bonus alanını aç, hediyeni gör ve gününe özel oynamaya başla.",
        ),
    ]
    extras = [
        (
            "Sadece sana özel",
            "Bu jest doğum gününe özeldir — hediyen hesabında seni bekliyor.",
        ),
        (
            "Bugün de fırsatlar açık",
            "Race, Bilet ve Manager etkinlikleriyle hediyeni daha keyifli değerlendir.",
        ),
    ]
    body = (
        f'<tr><td align="center" style="padding:4px 20px 8px;">{badge("DOĞUM GÜNÜ")}</td></tr>'
        + eyebrow("Kutlama")
        + headline("İyi ki doğdun, {{name}}")
        + hero_image(IMG_KASA, "Doğum Günü Hediyesi")
        + lead(
            "Doğum günün <strong style='color:#ffffff;'>kutlu olsun</strong>! "
            "Senin için özel bir doğum günü hediyesi hesabına eklendi."
        )
        + feature_box(
            kicker="★ Doğum günü hediyesi ★",
            big="HEDİYE HESABINDA",
            subtitle="Bugüne özel tanımlanan jest",
            note="Hediye bakiyene / bonus alanına işlendi. Detay için hesabına bak, günün tadını çıkar.",
        )
        + section_label("Nasıl?")
        + numbered_list(steps)
        + section_label("Gününe özel")
        + promo_cards(extras)
        + cta_row("Hediyemi Gör")
    )
    return {
        "name": "2026 · Doğum Günü Kutlaması",
        "subject": "{{name}}, iyi ki doğdun — hediyen hesabında seni bekliyor!",
        "html_body": shell(
            title="Makrobet Doğum Günü",
            preheader="Doğum günü hediyen hesabına eklendi",
            body_rows=body,
        ),
        "text_body": (
            "Merhaba {{name}},\n\n"
            "İyi ki doğdun!\n"
            "Doğum günü hediyen hesabına eklendi.\n"
            "1) Doğum günün kutlu olsun\n"
            "2) Hediye hesabında\n"
            "3) Hemen kontrol et\n\n"
            f"Hesaba git: {AFF}\n"
        ),
    }


def preset_etkinlik_tanitim() -> dict:
    """Sitedeki mevcut etkinlik / kampanya tanıtım mailingi."""
    live = [
        (
            "Amusnet Race",
            "Ödül havuzlu slot yarışı — sıralamaya gir, haftalık ödül payını kap.",
        ),
        (
            "Bilet Etkinliği",
            "Oynadıkça bilet biriktir; çekiliş ve özel ödül turlarına hak kazan.",
        ),
        (
            "Makro Manager",
            "Manager döneminde rolling hedeflerini tamamla, ekstra prim kazan.",
        ),
    ]
    always = [
        (
            "%100 Kayıp Bonusu",
            "Yatırımın kayba dönerse aynı tutarı tekrar hesabına ekleriz.",
        ),
        (
            "Arkadaşını Getir",
            "Davet ettiğin üye yatırım yaptıkça hem sen hem o bonus alır.",
        ),
        (
            "Makro Kasa & Prim",
            "Yatırıma ek kasa ve güncel prim / çevrim kampanyalarıyla bakiyeni büyüt.",
        ),
    ]
    body = (
        f'<tr><td align="center" style="padding:4px 20px 8px;">{badge("ETKİNLİKLER", solid=False)}</td></tr>'
        + eyebrow("Promosyonlar")
        + headline("Sitedeki etkinlikler seni bekliyor")
        + hero_image(IMG_RACE, "Makrobet Etkinlikleri")
        + lead(
            "Merhaba <strong style='color:#ffffff;'>{{name}}</strong> — Makrobet’te şu an "
            "aktif olan turnuva, bilet ve kampanya fırsatlarının kısa turu:"
        )
        + section_label("Canlı etkinlikler")
        + promo_cards(live)
        + section_label("Sürekli kampanyalar")
        + promo_cards(always)
        + lead(
            "Hepsi hesabında hazır. Tek tıkla siteye geç, katılmak istediğin etkinliği seç."
        )
        + cta_row("Etkinlikleri İncele")
    )
    return {
        "name": "2026 · Etkinlik Tanıtımı",
        "subject": "{{name}}, Race · Bilet · Manager ve daha fazlası seni bekliyor",
        "html_body": shell(
            title="Makrobet Etkinlik Tanıtımı",
            preheader="Sitedeki aktif etkinlik ve kampanyalar",
            body_rows=body,
        ),
        "text_body": (
            "Merhaba {{name}},\n\n"
            "Sitedeki etkinlikler:\n"
            "- Amusnet Race\n- Bilet Etkinliği\n- Makro Manager\n"
            "- %100 Kayıp Bonusu\n- Arkadaşını Getir\n- Makro Kasa & Prim\n\n"
            f"İncele: {AFF}\n"
        ),
    }


def preset_steril_ayricaliklar() -> dict:
    """MakroVip Club davet — çekim önde, promosyon sayfası harmanı."""
    vip_items = [
        (
            "Makro VIP Club & Ödüller",
            "Seviye atladıkça nakit ödül, prim ve VIP kasa ayrıcalıkları hesabında açılır.",
        ),
        (
            "Prim",
            "Seviye atla; 7 gün boyunca her gün nakit prim ödülünün tadını çıkar.",
        ),
        (
            "Makro Manager",
            "Manager döneminde rolling hedeflerini tamamla; ekstra prim ve ödül havuzundan payını al.",
        ),
    ]
    event_items = [
        (
            "Yarışlar",
            "Makrobet yarış ve turnuva sıralamasına gir; ödül havuzundan payını kap.",
        ),
        (
            "Bilet Etkinliği",
            "100.000 ₺ ödüllü bilet etkinliğinde oynadıkça bilet biriktir, çekilişe katıl.",
        ),
    ]
    body = (
        f'<tr><td align="center" style="padding:6px 20px 10px;">{badge("ÖZEL DAVET", glow=True)}</td></tr>'
        + eyebrow("MakroVip Club’a Davet")
        + headline("{{name}}, seni Makrobet’in özel dünyası bekliyor", size=23)
        + lead(
            "Hızlı çekim, 3.000 TL deneme kasası, %100 kayıp güvencesi, VIP ödülleri "
            "ve haftalık etkinlikler — hepsi tek davette.",
            size=15,
            emphasize=True,
        )
        + feature_box(
            kicker="★ Hızlı çekim ★",
            big="5 DK",
            subtitle="NET ÇEKİM",
            note="Kazancın net işlenir; çekim talebin dakikalar içinde sonuçlanır — bekletmeden hesabında.",
        )
        + feature_box_3000()
        + hero_image(IMG_KAYIP, "%100 Kayıp Bonusu", soft=True, glow=True)
        + feature_box(
            kicker="★ Güvence ★",
            big="%100",
            subtitle="KAYIP BONUSU",
            note="Yatırım senden, güvence Makrobet’ten — kaybın kadar bakiye yeniden tanımlanır.",
        )
        + section_label("VIP · Prim · Manager")
        + promo_cards(vip_items, highlight_first=1, pad_y=13)
        + section_label("Etkinlikler")
        + promo_cards(event_items, pad_y=12)
        + lead(
            "Tek tıkla kaydını tamamla; hızlı çekim, deneme kasası ve VIP avantajları "
            "hesabında seni bekler.",
            size=14,
        )
        + cta_row("Daveti Aç · Hemen Kayıt Ol", wide=True, font_px=16, pad="16px 36px", glow=True, gradient=True)
    )
    return {
        "name": "2026 · Steril · Ayrıcalıklar",
        "subject": "{{name}}, MakroVip Club’a davet — hızlı çekim · 3.000 TL · %100 kayıp",
        "html_body": shell(
            title="MakroVip Club’a Davet",
            preheader="Hızlı çekim · 3.000 TL deneme · %100 kayıp · VIP · Yarışlar · Bilet",
            body_rows=body,
        ),
        "text_body": (
            "Merhaba {{name}},\n\n"
            "MakroVip Club’a davet:\n"
            "• Hızlı çekim — talebin dakikalar içinde\n"
            "• 3.000 TL deneme kasası\n"
            "• %100 kayıp bonusu\n"
            "• Makro VIP Club & ödüller\n"
            "• Prim\n"
            "• Makro Manager\n"
            "• Yarışlar\n"
            "• Bilet etkinliği\n\n"
            f"Hemen kayıt: {AFF}\n"
        ),
    }


def preset_gorselsiz_ayricaliklar() -> dict:
    """MakroVip Club davet — aynı vurgu, promo hero görseli yok (sadece metin/kart)."""
    vip_items = [
        (
            "Makro VIP Club & Ödüller",
            "Seviye atladıkça nakit ödül, prim ve VIP kasa ayrıcalıkları hesabında açılır.",
        ),
        (
            "Prim",
            "Seviye atla; 7 gün boyunca her gün nakit prim ödülünün tadını çıkar.",
        ),
        (
            "Makro Manager",
            "Manager döneminde rolling hedeflerini tamamla; ekstra prim ve ödül havuzundan payını al.",
        ),
    ]
    event_items = [
        (
            "Yarışlar",
            "Makrobet yarış ve turnuva sıralamasına gir; ödül havuzundan payını kap.",
        ),
        (
            "Bilet Etkinliği",
            "100.000 ₺ ödüllü bilet etkinliğinde oynadıkça bilet biriktir, çekilişe katıl.",
        ),
    ]
    body = (
        f'<tr><td align="center" style="padding:6px 20px 10px;">{badge("ÖZEL DAVET", glow=True)}</td></tr>'
        + eyebrow("MakroVip Club’a Davet")
        + headline("{{name}}, seni Makrobet’in özel dünyası bekliyor", size=23)
        + lead(
            "Hızlı çekim, 3.000 TL deneme kasası, %100 kayıp güvencesi, VIP ödülleri "
            "ve haftalık etkinlikler — hepsi tek davette.",
            size=15,
            emphasize=True,
        )
        + feature_box(
            kicker="★ Hızlı çekim ★",
            big="5 DK",
            subtitle="NET ÇEKİM",
            note="Kazancın net işlenir; çekim talebin dakikalar içinde sonuçlanır — bekletmeden hesabında.",
        )
        + feature_box_3000()
        + feature_box(
            kicker="★ Güvence ★",
            big="%100",
            subtitle="KAYIP BONUSU",
            note="Yatırım senden, güvence Makrobet’ten — kaybın kadar bakiye yeniden tanımlanır.",
        )
        + section_label("VIP · Prim · Manager")
        + promo_cards(vip_items, highlight_first=1, pad_y=13)
        + section_label("Etkinlikler")
        + promo_cards(event_items, pad_y=12)
        + lead(
            "Tek tıkla kaydını tamamla; hızlı çekim, deneme kasası ve VIP avantajları "
            "hesabında seni bekler.",
            size=14,
        )
        + cta_row("Daveti Aç · Hemen Kayıt Ol", wide=True, font_px=16, pad="16px 36px", glow=True, gradient=True)
    )
    return {
        "name": "2026 · Görselsiz · Ayrıcalıklar",
        "subject": "{{name}}, MakroVip Club’a davet — hızlı çekim · 3.000 TL · %100 kayıp",
        "html_body": shell(
            title="MakroVip Club’a Davet",
            preheader="Hızlı çekim · 3.000 TL deneme · %100 kayıp · VIP · Yarışlar · Bilet",
            body_rows=body,
        ),
        "text_body": (
            "Merhaba {{name}},\n\n"
            "MakroVip Club’a davet:\n"
            "• Hızlı çekim — talebin dakikalar içinde\n"
            "• 3.000 TL deneme kasası\n"
            "• %100 kayıp bonusu\n"
            "• Makro VIP Club & ödüller\n"
            "• Prim\n"
            "• Makro Manager\n"
            "• Yarışlar\n"
            "• Bilet etkinliği\n\n"
            f"Hemen kayıt: {AFF}\n"
        ),
    }


PRESET_BUILDERS = (
    preset_davet_deneme_kayip,
    preset_steril_ayricaliklar,
    preset_gorselsiz_ayricaliklar,
    preset_davet_test,
    preset_davet_mailing,
    preset_pasif_uye,
    preset_memnuniyet,
    preset_ilk_yatirim,
    preset_turnuva,
    preset_yil_donumu,
    preset_dogum_gunu,
    preset_etkinlik_tanitim,
)


def build_all_presets() -> list[dict]:
    return [fn() for fn in PRESET_BUILDERS]
