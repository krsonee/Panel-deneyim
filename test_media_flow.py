import base64
import unittest

from io import BytesIO

from PIL import Image

import subprocess
from pathlib import Path

from media_bot import (
    MediaBot,
    _prepare_sticker,
    _read_draft,
    _reference_on_magenta,
    _to_video_sticker,
    _write_draft,
)
from media_brands import mascot_reference
from media_flow import (
    banner_motion_prompt,
    banner_prompt,
    campaign_prompt,
    new_session,
    revise_prompt,
    sticker_from_poster,
    sticker_motion_prompt,
    sticker_prompt,
    video_aspect,
    video_prompt,
    welcome_text,
)
import media_gemini
from media_gemini import extract_image, extract_images, image_parts, video_request_body


class FlowTests(unittest.TestCase):
    def test_mascot_photo_goes_before_the_prompt(self):
        parts = image_parts("edit this man", {"bytes": b"mascot", "mime": "image/png"}, image_first=True)
        self.assertIn("inlineData", parts[0])
        self.assertEqual(parts[1]["text"], "edit this man")

    def test_video_request_does_not_use_inline_data(self):
        body = video_request_body("animate the poster", b"not-a-real-image", "image/png", "9:16")
        image = body["instances"][0]["image"]
        self.assertIn("bytesBase64Encoded", image)
        self.assertNotIn("inlineData", image)
        self.assertEqual(body["parameters"]["aspectRatio"], "9:16")
        self.assertEqual(body["parameters"]["durationSeconds"], 4)

    def test_prompt_keeps_campaign_text_and_brand(self):
        session = new_session()
        session.update({
            "brand": "makrobet",
            "fmt": "1x1",
            "category": "casino",
            "campaign": "%100 Freespin Bonusu Seni Bekliyor!",
        })
        prompt = campaign_prompt(session)
        self.assertIn("%100 Freespin Bonusu Seni Bekliyor!", prompt)
        self.assertIn("official logo", prompt)
        self.assertIn("makrobet818.com", prompt)
        self.assertIn("Do not put each word on its own line", prompt)

        session["brand"] = "betced"
        prompt = campaign_prompt(session)
        self.assertIn("betced368.com", prompt)

    def test_revise_keeps_brand(self):
        session = new_session()
        session["brand"] = "betced"
        text = revise_prompt(session, "%100 yerine %500 yaz")
        self.assertIn("%100 yerine %500 yaz", text)
        self.assertIn("BETCED", text)

    def test_banner_prompt_keeps_headline_and_loops(self):
        session = new_session()
        session.update({
            "brand": "makrobet",
            "fmt": "16x9",
            "category": "casino",
            "campaign": "%100 Freespin Bonusu Seni Bekliyor!",
        })
        prompt = banner_prompt(session)
        self.assertIn("%100 Freespin Bonusu Seni Bekliyor!", prompt)
        self.assertIn("official logo", prompt)
        self.assertIn("makrobet818.com", prompt)
        self.assertIn("loop", prompt)
        motion = banner_motion_prompt(session)
        self.assertIn("seamless loop", motion)
        self.assertIn("MAKROBET", motion)

    def test_sticker_prompt_is_a_cutout_not_a_poster(self):
        session = new_session()
        session.update({
            "brand": "makrobet",
            "fmt": "1x1",
            "sticker_kind": "mascot",
            "slogan": "Promo kod geliyor",
            "character": "çevresinde freespin yağmuru olsun",
        })
        prompt = sticker_prompt(session)
        self.assertIn("Edit the attached photo", prompt)
        self.assertIn("#FF00FF", prompt)
        self.assertIn("Promo kod geliyor", prompt)
        self.assertIn("yellow hair", prompt)
        self.assertNotIn("official logo", prompt)

    def test_game_name_gets_theme_aware_props_not_generic_coins(self):
        session = new_session()
        session.update({
            "brand": "makrobet",
            "sticker_kind": "mascot",
            "game": "Sweet bonanza",
            "slogan": "Kod geliyor",
        })
        prompt = sticker_prompt(session)
        self.assertIn("never a new body", prompt)
        self.assertIn("Sweet bonanza", prompt)
        self.assertIn("own knowledge of this exact game's real theme", prompt)
        self.assertIn("candy and fruit for a sweets game", prompt)

    def test_mascotless_brand_game_name_is_also_theme_aware(self):
        # betced has no mascot photo, so this hits the generic (non-photo) sticker branch.
        session = new_session()
        session.update({
            "brand": "betced",
            "sticker_kind": "mascot",
            "game": "Big bass bonanza",
        })
        prompt = sticker_prompt(session)
        self.assertIn("never a replacement body", prompt)
        self.assertIn("own knowledge of this exact game's real theme", prompt)
        self.assertIn("water and fish for a fishing game", prompt)

    def test_mascot_sticker_allows_full_costume_and_scene_freedom(self):
        # Referans paket gösterdi ki aynı maskot kral/korsan/şampiyon kılığına
        # girebiliyor, kimliği (yüz/saç) hep aynı kalıyor. Kıyafeti artık kilitli değil.
        session = new_session()
        session.update({"brand": "makrobet", "sticker_kind": "mascot", "slogan": "Kod geliyor"})
        prompt = sticker_prompt(session)
        self.assertIn("yellow hair", prompt)
        self.assertIn("fully re-costume", prompt)
        self.assertIn("ribbon or badge graphic", prompt)
        self.assertNotIn("navy suit with gold trim", prompt)
        self.assertNotIn("only his pose and what he holds", prompt)

    def test_slot_name_does_not_replace_the_mascot(self):
        session = new_session()
        session.update({
            "brand": "makrobet",
            "sticker_kind": "mascot",
            "game": "Bigbass bonanza",
            "slogan": "Kod geliyor",
            "character": "makrobet maskotu cevresinde freespin yagmuru olsun",
        })
        prompt = sticker_prompt(session)
        self.assertIn("Edit the attached photo", prompt)
        self.assertIn("Do not draw a fox", prompt)
        self.assertIn("a fish", prompt)
        self.assertIn("Bigbass bonanza", prompt)
        self.assertIn("never a new body", prompt)
        self.assertIn("Kod geliyor", prompt)
        self.assertIn("freespin yagmuru", prompt)

    def test_sticker_cutout_drops_magenta_and_fits_telegram(self):
        image = Image.new("RGBA", (600, 400), (255, 0, 255, 255))
        for x in range(220, 380):
            for y in range(80, 320):
                image.putpixel((x, y), (20, 40, 140, 255))
        raw = BytesIO()
        image.save(raw, format="PNG")
        webp, cleaned = _prepare_sticker(raw.getvalue())
        self.assertTrue(cleaned)
        self.assertLessEqual(len(webp), 512 * 1024)
        sticker = Image.open(BytesIO(webp)).convert("RGBA")
        self.assertEqual(max(sticker.size), 512)
        self.assertEqual(sticker.getpixel((0, 0))[3], 0)
        self.assertGreater(sticker.getpixel((sticker.size[0] // 2, sticker.size[1] // 2))[3], 200)

    def test_mascot_reference_background_becomes_magenta(self):
        raw = mascot_reference("makrobet")
        self.assertIsNotNone(raw)
        cleaned = Image.open(BytesIO(_reference_on_magenta(raw["bytes"]))).convert("RGBA")
        width, height = cleaned.size
        corner = cleaned.getpixel((2, 2))
        self.assertLess(abs(corner[0] - 255) + corner[1] + abs(corner[2] - 255), 40)
        center = cleaned.getpixel((width // 2, int(height * 0.62)))
        self.assertGreater(abs(center[0] - 255) + center[1] + abs(center[2] - 255), 80)

    def test_sticker_draft_survives_without_the_chat_session(self):
        _write_draft(4242, b"webp-bytes", "makrobet", 7)
        draft = _read_draft(4242)
        self.assertEqual(draft["webp"], b"webp-bytes")
        self.assertEqual(draft["brand"], "makrobet")
        self.assertEqual(draft["user_id"], 7)

    def test_poster_sticker_skips_size_and_uses_campaign(self):
        session = new_session()
        session.update({
            "brand": "makrobet",
            "fmt": "16x9",
            "campaign": "%100 NAKİT BONUS BAŞLIYOR",
        })
        sticker_from_poster(session)
        self.assertEqual(session["fmt"], "1x1")
        self.assertEqual(session["sticker_kind"], "mascot")
        self.assertEqual(session["slogan"], "%100 NAKİT BONUS BAŞLIYOR")
        self.assertNotEqual(session["step"], "format")

    def test_result_buttons_are_video_gif_and_sticker(self):
        labels = [
            button["text"]
            for row in MediaBot("dummy")._result_keyboard()["inline_keyboard"]
            for button in row
        ]
        self.assertIn("Video üret", labels)
        self.assertIn("Banner gif", labels)
        self.assertIn("Sticker üret", labels)
        self.assertNotIn("Hareketlendir", labels)

    def test_sticker_motion_keeps_magenta_background(self):
        session = new_session()
        session.update({"brand": "makrobet", "slogan": "Promo kod geliyor"})
        prompt = sticker_motion_prompt(session)
        self.assertIn("#FF00FF", prompt)
        self.assertIn("Promo kod geliyor", prompt)
        self.assertIn("short loop", prompt)

    def test_video_sticker_is_vp9_and_under_telegram_limit(self):
        folder = Path("/tmp/stk-test")
        folder.mkdir(exist_ok=True)
        source = folder / "in.mp4"
        subprocess.run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "color=c=0xFF00FF:s=320x180:d=2",
                "-f", "lavfi", "-i", "color=c=0x14285A:s=80x120:d=2",
                "-filter_complex", "overlay=120:30",
                "-t", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                str(source),
            ],
            check=True,
        )
        webm = _to_video_sticker(source.read_bytes())
        self.assertIsNotNone(webm)
        self.assertLessEqual(len(webm), 256 * 1024)
        probe = subprocess.run(
            [
                "ffprobe", "-hide_banner", "-loglevel", "error",
                "-show_entries", "stream=codec_name,width,height",
                "-show_entries", "format=duration",
                "-of", "default=nw=1",
                "-i", "pipe:0",
            ],
            input=webm,
            capture_output=True,
            check=True,
        )
        text = probe.stdout.decode()
        self.assertIn("codec_name=vp9", text)
        self.assertTrue("width=512" in text or "height=512" in text)
        duration = float(text.split("duration=")[1].split()[0])
        self.assertLessEqual(duration, 3.0)

    def test_black_bars_are_cut_out_of_the_sticker(self):
        folder = Path("/tmp/stk-bars")
        folder.mkdir(exist_ok=True)
        source = folder / "bars.mp4"
        subprocess.run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "color=c=black:s=320x180:d=2",
                "-f", "lavfi", "-i", "color=c=0xFF00FF:s=160x100:d=2",
                "-f", "lavfi", "-i", "color=c=0xE8C36A:s=50x70:d=2",
                "-filter_complex", "[0][1]overlay=80:40[m];[m][2]overlay=120:55",
                "-t", "2", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                str(source),
            ],
            check=True,
        )
        webm = _to_video_sticker(source.read_bytes())
        self.assertIsNotNone(webm)
        probe = subprocess.run(
            [
                "ffprobe", "-hide_banner", "-loglevel", "error",
                "-show_entries", "stream=width,height",
                "-of", "default=nw=1", "-i", "pipe:0",
            ],
            input=webm,
            capture_output=True,
            check=True,
        )
        text = probe.stdout.decode()
        width = int(text.split("width=")[1].split()[0])
        height = int(text.split("height=")[1].split()[0])
        self.assertLess(width / height, 1.9)

    def test_all_black_video_is_not_sent_as_a_sticker(self):
        folder = Path("/tmp/stk-black")
        folder.mkdir(exist_ok=True)
        source = folder / "black.mp4"
        subprocess.run(
            [
                "ffmpeg", "-y", "-hide_banner", "-loglevel", "error",
                "-f", "lavfi", "-i", "color=c=black:s=160x160:d=1",
                "-t", "1", "-c:v", "libx264", "-pix_fmt", "yuv420p",
                str(source),
            ],
            check=True,
        )
        self.assertIsNone(_to_video_sticker(source.read_bytes()))

    def test_category_without_size_does_not_crash(self):
        bot = MediaBot("dummy")
        session = new_session()
        session["brand"] = "betced"
        session["category"] = "casino"
        self.assertIsNone(bot._campaign_help(session))
        session["fmt"] = "1x1"
        text = bot._campaign_help(session)
        self.assertIn("Betced", text)
        self.assertIn("Casino Promo", text)

    def test_choice_survives_a_second_bot_copy(self):
        first = MediaBot("dummy")
        second = MediaBot("dummy")
        session = first._begin(909091)
        session["brand"] = "betced"
        session["mode"] = "image"
        session["fmt"] = "16x9"
        session["step"] = "category"
        first._keep(909091)
        other = second._begin(909091)
        self.assertEqual(other["brand"], "betced")
        self.assertEqual(other["fmt"], "16x9")
        self.assertEqual(other["mode"], "image")
        self.assertIsNone(other.get("image"))

    def test_welcome_lists_video_and_banner(self):
        text = welcome_text()
        self.assertIn("video", text)
        self.assertIn("banner gif", text)
        self.assertIn("makrobet818.com", text)
        self.assertIn("betced368.com", text)

    def test_video_aspect_maps_square_to_landscape(self):
        self.assertEqual(video_aspect("1x1"), "16:9")
        self.assertEqual(video_aspect("16x9"), "16:9")
        self.assertEqual(video_aspect("9x16"), "9:16")

    def test_extract_image_from_output_field(self):
        raw = base64.b64encode(b"png-bytes").decode()
        found = extract_image({
            "id": "int_1",
            "output_image": {"data": raw, "mime_type": "image/png"},
        })
        self.assertEqual(found["bytes"], b"png-bytes")
        self.assertEqual(found["interaction_id"], "int_1")

    def test_extract_image_from_steps(self):
        raw = base64.b64encode(b"step-bytes").decode()
        found = extract_image({
            "id": "int_2",
            "steps": [{"content": [{"type": "image", "data": raw, "mime_type": "image/png"}]}],
        })
        self.assertEqual(found["bytes"], b"step-bytes")

    def test_extract_image_from_generate_content(self):
        raw = base64.b64encode(b"gen-bytes").decode()
        found = extract_image({
            "candidates": [{
                "content": {
                    "parts": [{
                        "inlineData": {"mimeType": "image/png", "data": raw},
                    }]
                }
            }]
        })
        self.assertEqual(found["bytes"], b"gen-bytes")
        self.assertEqual(found["mime"], "image/png")

    def test_extract_images_returns_every_candidate_in_order(self):
        raw_a = base64.b64encode(b"a-bytes").decode()
        raw_b = base64.b64encode(b"b-bytes").decode()
        found = extract_images({
            "candidates": [
                {"content": {"parts": [{"inlineData": {"mimeType": "image/png", "data": raw_a}}]}},
                {"content": {"parts": [{"inlineData": {"mimeType": "image/png", "data": raw_b}}]}},
            ]
        })
        self.assertEqual([item["bytes"] for item in found], [b"a-bytes", b"b-bytes"])

    def test_generate_image_sends_candidate_count_when_requested(self):
        captured = {}

        def fake_request(url, payload=None, timeout=120):
            captured["payload"] = payload
            raw = base64.b64encode(b"only-candidate").decode()
            return {"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "image/png", "data": raw}}]}}]}

        original = media_gemini._request
        media_gemini._request = fake_request
        try:
            media_gemini.generate_image("prompt", "1:1", candidates=3)
        finally:
            media_gemini._request = original
        self.assertEqual(captured["payload"]["generationConfig"]["candidateCount"], 3)

    def test_generate_image_defaults_do_not_send_candidate_count(self):
        captured = {}

        def fake_request(url, payload=None, timeout=120):
            captured["payload"] = payload
            raw = base64.b64encode(b"only-candidate").decode()
            return {"candidates": [{"content": {"parts": [{"inlineData": {"mimeType": "image/png", "data": raw}}]}}]}

        original = media_gemini._request
        media_gemini._request = fake_request
        try:
            media_gemini.generate_image("prompt", "1:1")
        finally:
            media_gemini._request = original
        self.assertNotIn("candidateCount", captured["payload"]["generationConfig"])

    def test_generate_image_picks_the_sharper_candidate(self):
        flat = Image.new("RGB", (64, 64), (128, 128, 128))
        flat_buf = BytesIO()
        flat.save(flat_buf, format="PNG")

        detailed = Image.new("RGB", (64, 64))
        pixels = detailed.load()
        for x in range(64):
            for y in range(64):
                pixels[x, y] = (255, 255, 255) if (x + y) % 2 == 0 else (0, 0, 0)
        detailed_buf = BytesIO()
        detailed.save(detailed_buf, format="PNG")

        raw_flat = base64.b64encode(flat_buf.getvalue()).decode()
        raw_detailed = base64.b64encode(detailed_buf.getvalue()).decode()

        def fake_request(url, payload=None, timeout=120):
            return {"candidates": [
                {"content": {"parts": [{"inlineData": {"mimeType": "image/png", "data": raw_flat}}]}},
                {"content": {"parts": [{"inlineData": {"mimeType": "image/png", "data": raw_detailed}}]}},
            ]}

        original = media_gemini._request
        media_gemini._request = fake_request
        try:
            best = media_gemini.generate_image("prompt", "1:1", candidates=2)
        finally:
            media_gemini._request = original
        self.assertEqual(best["bytes"], detailed_buf.getvalue())

    def test_video_request_defaults_skip_unsupported_negative_prompt(self):
        # veo-3.1-lite bu alanı reddediyor, o yüzden hiç env değişkeni yokken
        # negativePrompt gövdeye hiç eklenmemeli (bkz. gerçek Google hatası).
        body = video_request_body("animate the poster", b"not-a-real-image", "image/png", "16:9")
        params = body["parameters"]
        self.assertEqual(params["resolution"], "720p")
        self.assertNotIn("negativePrompt", params)
        self.assertNotIn("generateAudio", params)

    def test_video_request_sends_negative_prompt_only_when_configured(self):
        original = media_gemini.VIDEO_NEGATIVE_PROMPT
        media_gemini.VIDEO_NEGATIVE_PROMPT = "flicker, jitter"
        try:
            body = video_request_body("animate the poster", b"not-a-real-image", "image/png", "16:9")
        finally:
            media_gemini.VIDEO_NEGATIVE_PROMPT = original
        self.assertEqual(body["parameters"]["negativePrompt"], "flicker, jitter")

    def test_campaign_prompt_includes_professional_art_direction(self):
        session = new_session()
        session.update({
            "brand": "makrobet",
            "fmt": "1x1",
            "category": "casino",
            "campaign": "%100 Freespin Bonusu Seni Bekliyor!",
        })
        prompt = campaign_prompt(session)
        self.assertIn("cinematic studio lighting", prompt)
        self.assertIn("no melted, duplicated, or warped letters", prompt)

    def test_banner_prompt_includes_professional_art_direction(self):
        session = new_session()
        session.update({
            "brand": "makrobet",
            "fmt": "16x9",
            "category": "casino",
            "campaign": "%100 Freespin Bonusu Seni Bekliyor!",
        })
        prompt = banner_prompt(session)
        self.assertIn("cinematic studio lighting", prompt)
        self.assertIn("no melted, duplicated, or warped letters", prompt)

    def test_motion_prompts_include_professional_animation_direction(self):
        session = new_session()
        session.update({"brand": "makrobet", "fmt": "16x9", "slogan": "Kod geliyor"})
        for prompt in (
            sticker_motion_prompt(session),
            video_prompt(session),
            banner_motion_prompt(session),
        ):
            self.assertIn("ease-in/ease-out", prompt)
            self.assertIn("perfectly seamless loop", prompt)


if __name__ == "__main__":
    unittest.main()
