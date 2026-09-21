import base64
import unittest

from io import BytesIO

from PIL import Image

from media_bot import _prepare_sticker, _read_draft, _reference_on_magenta, _write_draft
from media_brands import mascot_reference
from media_flow import (
    banner_motion_prompt,
    banner_prompt,
    campaign_prompt,
    new_session,
    revise_prompt,
    sticker_prompt,
    video_aspect,
    welcome_text,
)
from media_gemini import extract_image


class FlowTests(unittest.TestCase):
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
        self.assertIn("Not a poster", prompt)
        self.assertIn("#FF00FF", prompt)
        self.assertIn("not text to print", prompt)
        self.assertIn("Promo kod geliyor", prompt)
        self.assertIn("yellow hair", prompt)
        self.assertNotIn("official logo", prompt)

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


if __name__ == "__main__":
    unittest.main()
