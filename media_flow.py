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
        f"as one compact block of two to four lines: \"{text}\". "
        "Do not put each word on its own line. "
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
    if kind != "object" and brand.get("mascot"):
        return _mascot_sticker_prompt(brand, slogan, game, character)
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
        parts.append("Subject is one original mascot character, centered.")
        if game:
            parts.append(
                f"Slot name is scenery around him, never a replacement body: {game}. "
                "Fish, coins, or reels may float beside him. Do not turn him into that game's creature."
            )
        if character:
            parts.append(f"Apply this to the same mascot. Do not switch characters: {character}.")
    if slogan:
        parts.append(
            f"The only text is this short slogan, spelled exactly, on a small sign: \"{slogan}\"."
        )
    else:
        parts.append("No text anywhere in the image.")
    parts.append("No photorealistic celebrity.")
    return " ".join(parts)


def _mascot_sticker_prompt(brand, slogan, game, character):
    parts = [
        "Edit the attached photo into one Telegram sticker.",
        "The man already in the photo is the sticker. Do not invent a new character.",
        "Do not draw a fox, a cat, a fish, a dragon, a bird, or any cartoon animal.",
        "Keep his swept yellow hair, his face, his navy suit with gold trim, his white shirt, and his dark tie.",
        "You may change only his pose and what he holds.",
        "Replace the photo background with flat magenta #FF00FF.",
        "No frame, no poster, no website, no extra headline.",
        "He floats in the middle and does not touch the edges.",
        f"Palette around him: {brand['colors']}.",
    ]
    if game:
        parts.append(
            f"Slot name is scenery around this same man, never a new body: {game}. "
            "Fish, coins, or reels may float beside him."
        )
    if character:
        parts.append(f"Apply this to the same man. Do not switch characters: {character}.")
    if slogan:
        parts.append(f'The only text is this short slogan, spelled exactly, on a small sign in his hand: "{slogan}".')
    else:
        parts.append("No text anywhere in the image.")
    return " ".join(parts)


def sticker_motion_prompt(session):
    slogan = (session.get("slogan") or "").strip()
    text = f'The sign text stays exactly "{slogan}". ' if slogan else "Do not add text. "
    return (
        "Animate this sticker in place as a short loop. "
        "Keep the same character, the same face, and the same pose. "
        "Keep the flat magenta background exactly #FF00FF. "
        "Do not replace it with a room, a poster, or a new scene. "
        "Motion only: he blinks, he bounces slightly, coins or fish drift around him, and the slogan sign blinks. "
        "Do not change who he is. "
        f"{text}"
        "No camera move, no voice, no new words."
    )


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
        f"as one compact block of two to four lines: \"{text}\". "
        "Do not put each word on its own line. "
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
