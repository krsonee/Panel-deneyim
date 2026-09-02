"""makroz.ink kısa host olarak tanınsın — DNS yetmez, Kısa Link listesinde de olmalı."""
from __future__ import annotations

import os
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))
os.environ.setdefault("PANEL_BRAND", "makro")
os.environ.setdefault("SERVICE_MODE", "panel")


class MakrozInkHostTests(unittest.TestCase):
    def test_is_makrolink_host_without_db(self):
        import makrolink_api

        self.assertTrue(makrolink_api.is_makrolink_host("makroz.ink", None))
        self.assertTrue(makrolink_api.is_makrolink_host("www.makroz.ink", None))
        self.assertFalse(makrolink_api.is_makrolink_host("takipmkr.onrender.com", None))

    def test_ensure_merges_without_wiping(self):
        import makrolink_api
        from database import get_db, init_db as db_init

        db_init()
        with get_db() as conn:
            makrolink_api.upsert_setting(conn, "short_hosts", "makrosms.com\nmakrovip.com")
            makrolink_api.upsert_setting(conn, "public_host", "makrosms.com")
            changed = makrolink_api.ensure_brand_short_hosts(conn)
            self.assertTrue(changed)
            cfg = makrolink_api.get_config(conn)
        self.assertIn("makrosms.com", cfg["short_hosts"])
        self.assertIn("makrovip.com", cfg["short_hosts"])
        self.assertIn("makroz.ink", cfg["short_hosts"])
        self.assertEqual(cfg["public_host"], "makrosms.com")

    def test_unknown_code_on_makroz_uses_makrolink_404(self):
        from app import app

        client = app.test_client()
        res = client.get("/abc123xyz", headers={"Host": "makroz.ink"}, follow_redirects=False)
        self.assertEqual(res.status_code, 404)
        self.assertIn("Link bulunamadı", res.get_data(as_text=True))

    def test_root_on_makroz_is_not_admin_login(self):
        from app import app

        client = app.test_client()
        res = client.get("/", headers={"Host": "makroz.ink"}, follow_redirects=False)
        loc = (res.headers.get("Location") or "")
        self.assertNotIn("/admin", loc)
        self.assertEqual(res.status_code, 404)

    def test_canonical_panel_root_still_goes_admin(self):
        from app import app

        client = app.test_client()
        res = client.get("/", headers={"Host": "takipmkr.onrender.com"}, follow_redirects=False)
        self.assertEqual(res.status_code, 302)
        self.assertIn("/admin", res.headers.get("Location") or "")


if __name__ == "__main__":
    unittest.main()
