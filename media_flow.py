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
    slogan = (session.get("slogan") or "").strip()
    game = (session.get("game") or "").strip()
    character = (session.get("character") or "").strip()
    kind = session.get("sticker_kind") or "mascot"
    brand = BRANDS[session["brand"]]
    parts = [
        "Create one die-cut Telegram sticker of a single subject.",
        "Not a poster, not a banner, not a card, not an advertisement layout.",
        "No frame, no border, no rectangle, no button, no website, no headline.",
        "Background is only flat pure magenta #FF00FF, the same empty background as the reference.",
        "The subject floats in the middle and does not touch the edges.",
        "The scene description below is what the subject is doing. It is not text to print.",
        "Do not add any words except the slogan line, if one is given.",
    ]
    if kind == "object":
        parts.append(f"Subject is one object, not a person: {character or game or 'a casino chip'}.")
    else:
        if brand.get("mascot"):
            parts.append(
                "The attached image is the official mascot. "
                "Keep his face and swept yellow hair the same. "
                "He may change outfit, pose, and what he holds. "
                "Do not replace him with a different character. "
                "Do not copy the reference background. Output background stays flat magenta #FF00FF."
            )
        else:
            parts.append("Subject is one original mascot character, centered.")
        if game:
            parts.append(f"Theme, as a scene only, not as a logo and not as printed text: {game}.")
        if character:
            parts.append(f"Scene, not printed text: {character}.")
    if slogan:
        parts.append(
            f"The only text is this short slogan, spelled exactly, on a small sign: \"{slogan}\"."
        )
    else:
        parts.append("No text anywhere in the image.")
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


def sticker_from_poster(session):
    """Hazır afişten sticker: boyut sormadan, kampanya yazısı slogan olur."""
    text = (session.get("campaign") or "").strip()
    session["mode"] = "sticker"
    session["fmt"] = "1x1"
    session["sticker_kind"] = "mascot"
    session["game"] = ""
    session["slogan"] = text[:60]
    session["character"] = "elinde küçük tabela tutan maskot"
    return session


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
