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
        "Create one finished betting campaign poster at the requested aspect ratio. "
        "The attached image is the official logo. Place that logo unchanged. Do not redraw or retype the brand name. "
        f"Small website line, spelled exactly: {brand['domain']}. "
        f"Palette: {brand['colors']}. "
        f"Category: {category}. "
        "Render this Turkish headline exactly, with the same spelling and punctuation, "
        f"as the largest text: \"{text}\". "
        "Add a button that says HEMEN DENE. Add a small 18+ mark. "
        "Do not add any other words, especially not English slogans. "
        "High-end commercial layout, sharp type, not clipart."
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
        "Create one finished betting advertisement at the requested aspect ratio.",
        "High-end commercial poster, sharp lighting, not a cheap cartoon and not clipart.",
        "The attached image is the official logo. Place that logo unchanged. Do not redraw the letters.",
        f"Palette: {brand['colors']}.",
        "Do not invent extra text. No English words such as FREE SPINS unless they are inside the slogan below.",
    ]
    if kind == "object":
        parts.append(f"Subject is an object, not a person: {character or game or 'casino chip'}.")
    else:
        if brand.get("mascot"):
            parts.append(
                "The second attached image is the official Makrobet mascot. "
                "Keep the same 3D character: swept yellow hair, friendly face, navy suit with gold trim, white shirt, dark tie. "
                "Only change his outfit, pose, and scene to match the request. "
                "Do not replace him with Zeus, a fisherman, or any other character."
            )
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
    parts.append("No photorealistic celebrity.")
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


def banner_prompt(session):
    brand = BRANDS[session["brand"]]
    category = CATEGORIES[session["category"]]
    text = (session.get("campaign") or "").strip()
    return (
        "Create one finished website banner advertisement at the requested aspect ratio. "
        "The attached image is the official logo. Place that logo unchanged. Do not redraw or retype the brand name. "
        f"Small website line, spelled exactly: {brand['domain']}. "
        f"Palette: {brand['colors']}. "
        f"Category: {category}. "
        "This frame will loop as a banner, so keep the layout stable and the headline readable. "
        "Render this Turkish headline exactly, with the same spelling and punctuation, "
        f"as the largest text: \"{text}\". "
        "Add a button that says HEMEN DENE. Add a small 18+ mark. "
        "Do not add any other words, especially not English slogans. "
        "High-end commercial banner, sharp type, not clipart."
    )


def banner_motion_prompt(session):
    brand = BRANDS[session["brand"]]
    return (
        "Turn this banner into a short seamless loop. "
        "Keep the same framing, the same Turkish headline, and the same brand "
        f"{brand['wordmark']}. "
        "Motion stays inside the banner: a soft light sweep, a small glow on the button, a few sparks. "
        "Do not change the words. No new scenes, no camera cut, no voiceover."
    )


def video_aspect(fmt_key):
    """Veo kare üretmez. 1:1 ve 16:9 yatay, 9:16 dikey gider."""
    if fmt_key == "9x16":
        return "9:16"
    return "16:9"


def welcome_text():
    lines = ["Merhaba.", "", "Hangi marka?", ""]
    for key, brand in BRANDS.items():
        lines.append(f"• {brand['name']} — {brand['domain']}")
    lines.append("")
    lines.append("Sonra görsel, video, sticker ya da banner gif seç.")
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
