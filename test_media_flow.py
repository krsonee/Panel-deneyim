import base64
import unittest

from media_flow import campaign_prompt, new_session, revise_prompt, video_aspect
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
        self.assertIn("MAKROBET", prompt)
        self.assertIn("makrobet.com", prompt)

        session["brand"] = "betced"
        prompt = campaign_prompt(session)
        self.assertIn("BETCED", prompt)
        self.assertIn("betced.com", prompt)

    def test_revise_keeps_brand(self):
        session = new_session()
        session["brand"] = "betced"
        text = revise_prompt(session, "%100 yerine %500 yaz")
        self.assertIn("%100 yerine %500 yaz", text)
        self.assertIn("BETCED", text)

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
