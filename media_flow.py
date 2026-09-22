"""Medya botunun metinleri ve oturum adımları. Ağ çağrısı yok."""

from media_brands import BRANDS, CATEGORIES, FORMATS

# Bu iki blok her görsel promptuna eklenir. Amatör/AI görünümünün asıl kaynağı
# genelde eksik sanat yönetimi talimatıdır: ışık, derinlik, malzeme gerçekçiliği
# ve tipografi kalitesi tarif edilmezse model düz, clipart gibi bir sonuca gider.
POSTER_ART_DIRECTION = (
    "Shoot this like a top-tier iGaming ad agency campaign, not a template. "
    "Use cinematic studio lighting with a soft key light, a subtle rim light, and believable "
    "contact shadows. Build real depth: a sharp, in-focus foreground subject and message area, "
    "and a slightly blurred, complementary background layer for parallax feel. "
    "Grade the colors cohesively around the brand palette with a premium, high-dynamic-range look. "
    "Compose with clear visual hierarchy, rule-of-thirds balance, and generous breathing room "
    "around the headline and the logo."
)

ANTI_ARTIFACT_DIRECTION = (
    "Avoid every common AI rendering flaw: no melted, duplicated, or warped letters, no illegible "
    "or blurry type, no double-edged or smeared logo, no mismatched lighting between the logo and "
    "the scene, no visible seams, no stray watermark text, no extra or malformed fingers or limbs, "
    "no waxy plastic skin texture, no random unreadable background text."
)

STICKER_ART_DIRECTION = (
    "Render it like a premium, best-selling Telegram sticker pack: clean bold outline, vibrant "
    "cel-shaded lighting with one clear light source, crisp edge definition, and rich color depth. "
    "Keep every proportion consistent with a professional character design, not a rough sketch."
)

MOTION_ART_DIRECTION = (
    "Animate with professional motion-graphics polish: smooth ease-in/ease-out timing, no jitter, "
    "no flicker, no frame-to-frame morphing of the character, logo, or text, and a perfectly seamless "
    "loop where the last frame matches the first."
)


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
        f"{POSTER_ART_DIRECTION} "
        "Render this Turkish headline exactly, with the same spelling and punctuation, "
        f"as one compact block of two to four lines: \"{text}\". "
        "Do not put each word on its own line. Use confident, on-brand professional typography "
        "with consistent kerning and a clear baseline; the headline must stay perfectly legible. "
        "Add a button that says HEMEN DENE, styled as a real pressable UI button with depth, not flat text. "
        "Add a small 18+ mark. "
        "Do not add any other words, especially not English slogans. "
        f"{ANTI_ARTIFACT_DIRECTION} "
        "High-end commercial layout, sharp type, not clipart."
    )


def revise_prompt(session, note):
    brand = BRANDS[session["brand"]]
    return (
        "Edit the existing poster. Apply only this change: "
        f"{note.strip()}. "
        f"Keep the brand {brand['wordmark']} and {brand['domain']}. "
        "Keep every other word, person, and layout the same. "
        "Headline language stays Turkish. Do not redesign the whole image. "
        f"{ANTI_ARTIFACT_DIRECTION}"
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
        STICKER_ART_DIRECTION,
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
                "Use your own knowledge of this exact game's real theme, colors, and iconic symbols "
                "for the props and background — candy and fruit for a sweets game, water and fish for "
                "a fishing game, gold and temple carvings for a mythology game, and so on. Match what "
                "this specific game is actually about, not a generic pile of coins or a spinning reel. "
                "Do not turn him into that game's creature. "
                "Never write this game's own name or logo as text anywhere in the image — theme, colors, "
                "and objects only, no title lettering for the game itself."
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
    parts.append(ANTI_ARTIFACT_DIRECTION)
    return " ".join(parts)


def _mascot_sticker_prompt(brand, slogan, game, character):
    parts = [
        "Edit the attached photo into one rich, professional Telegram sticker.",
        "The man already in the photo is the sticker. Do not invent a new character.",
        "Do not draw a fox, a cat, a fish, a dragon, a bird, or any cartoon animal.",
        "Keep his exact face and his swept yellow hair so he stays instantly recognizable — this part is not negotiable.",
        "Everything else about his look is flexible: fully re-costume his outfit over or instead of his suit, "
        "change his pose, change what he holds, and add one or two extra themed elements around him if they "
        "fit the theme below — a small sidekick character, a treasure chest, a gift box, a spinning prize wheel, "
        "coins, confetti, or ribbons. For example a general promo or event theme can add a small gold crown and "
        "a royal coat over his suit; a pirate theme can dress him as a ship captain with a coat and hat; a "
        "strength or big-win theme can show him as a muscular champion holding a trophy and a belt. "
        "Pick whichever look fits the theme best, the way a professional character illustrator would.",
        "Replace the photo background with flat magenta #FF00FF.",
        "No frame, no poster border, no website address, no fake app screen — this stays one sticker graphic, not an ad layout.",
        "He (and any small sidekick or prop) floats in the middle and does not touch the edges.",
        f"Palette around him: {brand['colors']}.",
        STICKER_ART_DIRECTION,
        "Keep his facial proportions natural even in a new costume; do not distort his face or hands.",
    ]
    if game:
        parts.append(
            f"Slot name is scenery around this same man, never a new body: {game}. "
            "Use your own knowledge of this exact game's real theme, colors, and iconic symbols for "
            "the props and background — candy and fruit for a sweets game, water and fish for a "
            "fishing game, gold and temple carvings for a mythology game, and so on. Match what this "
            "specific game is actually about, not a generic pile of coins or a spinning reel. "
            "Never write this game's own name or logo as text anywhere in the image — theme, colors, "
            "and objects only, no title lettering for the game itself."
        )
    if character:
        parts.append(f"Apply this to the same man. Do not switch characters: {character}.")
    if slogan:
        parts.append(
            f'Add one bold, on-brand ribbon or badge graphic carrying this exact short text, spelled '
            f'exactly: "{slogan}". Design it like a real piece of graphic design — a banner or badge '
            "shape, brand colors, clean bold lettering — not plain floating text."
        )
    else:
        parts.append("No text anywhere in the image.")
    parts.append(ANTI_ARTIFACT_DIRECTION)
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
        f"{MOTION_ART_DIRECTION} "
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
        f"{MOTION_ART_DIRECTION} "
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
        f"{POSTER_ART_DIRECTION} "
        "This frame will loop as a banner, so keep the layout stable and the headline readable. "
        "Render this Turkish headline exactly, with the same spelling and punctuation, "
        f"as one compact block of two to four lines: \"{text}\". "
        "Do not put each word on its own line. Use confident, on-brand professional typography "
        "with consistent kerning and a clear baseline; the headline must stay perfectly legible. "
        "Add a button that says HEMEN DENE, styled as a real pressable UI button with depth, not flat text. "
        "Add a small 18+ mark. "
        "Do not add any other words, especially not English slogans. "
        f"{ANTI_ARTIFACT_DIRECTION} "
        "High-end commercial banner, sharp type, not clipart."
    )


def banner_motion_prompt(session):
    brand = BRANDS[session["brand"]]
    return (
        "Turn this banner into a short seamless loop. "
        "Keep the same framing, the same Turkish headline, and the same brand "
        f"{brand['wordmark']}. "
        "Motion stays inside the banner: a soft light sweep, a small glow on the button, a few sparks. "
        f"{MOTION_ART_DIRECTION} "
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
