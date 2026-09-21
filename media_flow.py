"""Medya botunun metinleri ve oturum adımları. Ağ çağrısı yok."""

from media_brands import BRANDS, CATEGORIES, FORMATS


def new_session():
    return {
        "brand": None,
        "mode": None,
        "fmt": None,
        "category": None,
        "campaign": "",
        "step": "brand",
        "interaction_id": None,
        "sticker_kind": None,
        "game": "",
        "slogan": "",
        "character": "",
    }


def campaign_prompt(session):
    brand = BRANDS[session["brand"]]
    category = CATEGORIES[session["category"]]
    text = (session.get("campaign") or "").strip()
    return (
        "Create one finished online-betting campaign poster. "
        f"Brand name to render exactly: {brand['wordmark']}. "
        f"Small website line: {brand['domain']}. "
        f"Palette: {brand['colors']}. "
        f"Category: {category}. "
        "Render this Turkish headline exactly, with the same spelling, accents, and punctuation, "
        f"as the largest text: \"{text}\". "
        "Add a clear button that says HEMEN DENE. "
        "Add a small 18+ mark. "
        "Do not replace the brand, do not translate the headline, do not add a different company name. "
        "Sharp commercial layout, readable type, no extra paragraphs."
    )


def revise_prompt(session, note):
    brand = BRANDS[session["brand"]]
    return (
        "Edit the existing poster. Apply only this change: "
        f"{note.strip()}. "
        f"Keep the brand {brand['wordmark']} and {brand['domain']}. "
        "Keep every other word, person, and layout the same. "
        "Headline language stays Turkish. Do not redesign the whole image."
    )


def sticker_prompt(session):
    brand = BRANDS[session["brand"]]
    slogan = (session.get("slogan") or "").strip()
    game = (session.get("game") or "").strip()
    character = (session.get("character") or "").strip()
    kind = session.get("sticker_kind") or "mascot"
    parts = [
        "Create one Telegram sticker illustration on a plain flat background.",
        f"Brand wordmark {brand['wordmark']} small at the bottom.",
        f"Style reference colors: {brand['colors']}.",
    ]
    if kind == "object":
        parts.append(f"Subject is an object, not a person: {character or game or 'casino chip'}.")
    else:
        parts.append("Subject is a single mascot character, centered, full body or bust.")
        if game:
            parts.append(f"Inspired by the public slot theme name only as a description, not a copied logo: {game}.")
        if character:
            parts.append(f"Character details: {character}.")
    if slogan:
        parts.append(f"Short text on the sticker, spelled exactly: \"{slogan}\".")
    else:
        parts.append("No extra slogan text.")
    parts.append("No photorealistic celebrity. No copied trademark artwork.")
    return " ".join(parts)


def video_prompt(session):
    brand = BRANDS[session["brand"]]
    return (
        "Animate this existing campaign poster in place. "
        "Keep the same framing, the same Turkish headline, and the same brand "
        f"{brand['wordmark']}. "
        "Add a short subtle motion: light glow, a few coins or sparks, gentle camera push. "
        "Do not change the words. No new scenes, no voiceover speech."
    )


def video_aspect(fmt_key):
    """Veo kare üretmez. 1:1 ve 16:9 yatay, 9:16 dikey gider."""
    if fmt_key == "9x16":
        return "9:16"
    return "16:9"


def welcome_text():
    lines = ["Merhaba.", "", "Hangi marka için görsel üreteyim?", ""]
    for key, brand in BRANDS.items():
        lines.append(f"• {brand['name']} — {brand['domain']}")
    lines.append("")
    lines.append("Marka seç, sonra görsel ya da sticker.")
    return "\n".join(lines)


def ready_caption(session, filename):
    brand = BRANDS[session["brand"]]
    fmt = FORMATS[session["fmt"]][1]
    category = CATEGORIES[session["category"]]
    return (
        f"Görsel hazır.\n"
        f"{brand['name']} · {category} · {fmt}\n"
        f"{filename}"
    )
