"""Bizzo panel: kapalı bizzocasino izleri silinir, marka Betced olur, kısa link alanı kalır."""
from __future__ import annotations

import os
import tempfile
import unittest
from contextlib import closing
from pathlib import Path

# Testler Bizzo panel bağlamında çalışır
os.environ["PANEL_BRAND"] = "bizzo"
os.environ.pop("DATABASE_URL", None)

import database  # noqa: E402
import makrolink_api  # noqa: E402
import panel_config  # noqa: E402
import track_domains  # noqa: E402


PANEL_FILES = (
    Path("panel_config.py"),
    Path("templates/admin.html"),
    Path("static/biolink.js"),
    Path("track_domains.py"),
)


class BetcedRebrandTests(unittest.TestCase):
    def test_brand_is_betced_not_bizzocasino_site(self):
        self.assertEqual(panel_config.PANEL_BRAND, "bizzo")
        brand = panel_config.BRAND
        self.assertEqual(brand["casino_name"], "Betced")
        self.assertEqual(brand["tagline"], "Betced Yönetim")
        self.assertEqual(brand["product_name"], "BizzoPanel")
        self.assertEqual(brand["default_tracked_domains"], [])
        self.assertFalse(brand["biolink_pack"].get("site_url"))
        self.assertEqual(brand["biolink_pack"]["handle"], "betced")
        self.assertEqual(brand["biolink_pack"]["bonus_kicker"], "BETCED KAMPANYA")
        self.assertEqual(brand["biolink_pack"]["link_default_label"], "Betced'e Git")
        self.assertEqual(brand["domain_prefix_placeholder"], "betced")
        self.assertEqual(brand["shortlink_max_hosts"], 4)
        blob = str(brand).lower()
        self.assertNotIn("bizzocasino168", blob)
        self.assertNotIn("bizzocasino.com", blob)

    def test_panel_brand_aliases_still_map_to_bizzo(self):
        src = Path("panel_config.py").read_text(encoding="utf-8")
        self.assertIn('"bizzo", "bizzocasino", "bizzo-casino"', src)

    def test_retired_host_matcher(self):
        hit = track_domains.is_retired_bizzo_casino_host
        self.assertTrue(hit("bizzocasino168.com"))
        self.assertTrue(hit("https://www.bizzocasino168.com/promos"))
        self.assertTrue(hit("WWW.BIZZOCASINO.COM"))
        self.assertFalse(hit(""))
        self.assertFalse(hit("betced.com"))
        self.assertFalse(hit("kisalink1.com"))

    def test_source_files_drop_old_casino_domain(self):
        for path in PANEL_FILES:
            text = path.read_text(encoding="utf-8")
            self.assertNotIn("bizzocasino168", text, f"{path} still has bizzocasino168")
            self.assertNotIn("www.bizzocasino", text, f"{path} still has www.bizzocasino")

    def test_admin_keeps_shortlink_ui(self):
        html = Path("templates/admin.html").read_text(encoding="utf-8")
        self.assertIn("makrolink-hosts-manager", html)
        self.assertIn("Kısa domainler", html)
        self.assertIn("Kısalt &amp; kopyala", html)
        self.assertIn("betced.com", html)


class BetcedPurgeTests(unittest.TestCase):
    def setUp(self):
        self._tmpdir = tempfile.TemporaryDirectory(prefix="betced-purge-")
        self.db_path = Path(self._tmpdir.name) / "test.db"
        self._orig_path = database.DB_PATH
        database.DB_PATH = self.db_path
        database.init_db()
        with closing(database.get_db()) as conn:
            now = "2026-09-10T00:00:00Z"
            database.execute(
                conn,
                "INSERT INTO tracked_links (domain, ref_code, label, created_at, created_by, redirect_url) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("bizzocasino168.com", "", "eski site", now, "test", ""),
            )
            database.execute(
                conn,
                "INSERT INTO tracked_links (domain, ref_code, label, created_at, created_by, redirect_url) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("giris-ornek.com", "", "giriş", now, "test", "https://www.bizzocasino168.com"),
            )
            database.execute(
                conn,
                "INSERT INTO tracked_links (domain, ref_code, label, created_at, created_by, redirect_url) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("keep-me.com", "", "kalacak", now, "test", "https://betced.com"),
            )
            database.execute(
                conn,
                "INSERT INTO biolink_pages (slug, title, created_at, updated_at, custom_domain) "
                "VALUES (?, ?, ?, ?, ?)",
                ("eski", "Eski", now, now, "www.bizzocasino168.com"),
            )
            page = database.fetchone(conn, "SELECT id FROM biolink_pages WHERE slug = ?", ("eski",))
            database.execute(
                conn,
                "INSERT INTO biolink_buttons (page_id, button_type, label, url, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                (page["id"], "link", "Site", "https://bizzocasino168.com/bonus", now, now),
            )
            makrolink_api.upsert_setting(conn, "short_hosts", "bizzocasino168.com\nkisalink1.com")
            makrolink_api.upsert_setting(conn, "public_host", "bizzocasino168.com")
            makrolink_api.upsert_setting(conn, "online_domain_group", "bizzocasino168.com\nkeep-me.com")
            database.execute(
                conn,
                "INSERT INTO makrolink_links (code, destination_url, label, created_at, updated_at, short_host) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("eski168", "https://bizzocasino168.com/?x=1", "eski", now, now, "kisalink1.com"),
            )
            database.execute(
                conn,
                "INSERT INTO makrolink_links (code, destination_url, label, created_at, updated_at, short_host) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                ("kalir", "https://betced.com/ok", "yeni", now, now, "kisalink1.com"),
            )
            conn.commit()

    def tearDown(self):
        database.DB_PATH = self._orig_path
        self._tmpdir.cleanup()

    def test_purge_removes_bizzocasino_keeps_others(self):
        self.assertEqual(panel_config.PANEL_BRAND, "bizzo")
        track_domains.purge_retired_bizzo_casino_domains()
        with closing(database.get_db()) as conn:
            domains = {
                r["domain"]
                for r in database.fetchall(conn, "SELECT domain FROM tracked_links")
            }
            self.assertNotIn("bizzocasino168.com", domains)
            self.assertIn("giris-ornek.com", domains)
            self.assertIn("keep-me.com", domains)
            redir = database.fetchone(
                conn, "SELECT redirect_url FROM tracked_links WHERE domain = ?", ("giris-ornek.com",)
            )
            self.assertEqual((redir["redirect_url"] or ""), "")
            page = database.fetchone(conn, "SELECT custom_domain FROM biolink_pages WHERE slug = ?", ("eski",))
            self.assertEqual((page["custom_domain"] or ""), "")
            btn = database.fetchone(conn, "SELECT url FROM biolink_buttons WHERE label = ?", ("Site",))
            self.assertEqual((btn["url"] or ""), "")
            hosts = (makrolink_api.get_setting(conn, "short_hosts", "") or "")
            self.assertNotIn("bizzocasino", hosts.lower())
            self.assertIn("kisalink1.com", hosts)
            pub = makrolink_api.get_setting(conn, "public_host", "") or ""
            self.assertEqual(pub, "kisalink1.com")
            group = makrolink_api.get_setting(conn, "online_domain_group", "") or ""
            self.assertNotIn("bizzocasino", group.lower())
            self.assertIn("keep-me.com", group)
            codes = {
                r["code"]
                for r in database.fetchall(conn, "SELECT code FROM makrolink_links")
            }
            self.assertNotIn("eski168", codes)
            self.assertIn("kalir", codes)

    def test_makro_brand_does_not_purge(self):
        orig = panel_config.PANEL_BRAND
        panel_config.PANEL_BRAND = "makro"
        try:
            track_domains.purge_retired_bizzo_casino_domains()
        finally:
            panel_config.PANEL_BRAND = orig
        with closing(database.get_db()) as conn:
            row = database.fetchone(
                conn, "SELECT id FROM tracked_links WHERE domain = ?", ("bizzocasino168.com",)
            )
            self.assertIsNotNone(row)


if __name__ == "__main__":
    unittest.main()
