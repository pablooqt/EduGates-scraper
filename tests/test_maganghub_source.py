import unittest
import os
from unittest.mock import MagicMock
from src.sources.maganghub import MagangHubSource


class TestMagangHubSource(unittest.TestCase):

    def setUp(self):
        self.source = MagangHubSource()
        self.fixtures_dir = os.path.join(os.path.dirname(__file__), "fixtures")
        
        with open(os.path.join(self.fixtures_dir, "maganghub_listing.html"), "r", encoding="utf-8") as f:
            self.listing_html = f.read()

        with open(os.path.join(self.fixtures_dir, "maganghub_detail.html"), "r", encoding="utf-8") as f:
            self.detail_html = f.read()

    def test_discover_pagination(self):
        mock_client = MagicMock()
        mock_client.get.return_value = self.listing_html
        
        pag_info = self.source.discover_pagination(mock_client)
        self.assertEqual(pag_info["total"], 28455)
        self.assertEqual(pag_info["per_page"], 18)
        self.assertEqual(pag_info["last_page"], 1581)
        self.assertEqual(pag_info["sort_param"], "sort=most_quota")

    def test_parse_listing(self):
        items = self.source.parse_listing(self.listing_html)
        self.assertEqual(len(items), 18)
        
        item1 = items[0]
        self.assertEqual(item1["source"], "maganghub")
        self.assertEqual(item1["source_id"], "a240f2ba-12c0-4958-b416-c3e9c1d4e344")
        self.assertEqual(item1["judul"], "PSIKOLOG")
        self.assertNotIn("slug", item1)
        self.assertEqual(item1["perusahaan_nama"], "RUMAH TAHANAN NEGARA KELAS IIB SIBUHUAN")
        self.assertEqual(item1["lokasi"], "Kab. Padang Lawas")
        self.assertNotIn("durasi", item1)
        self.assertEqual(item1["kuota"], 1)
        self.assertEqual(item1["status"], "Aktif")

    def test_parse_detail(self):
        detail = self.source.parse_detail(self.detail_html)
        self.assertEqual(detail["judul"], "PSIKOLOG")
        self.assertTrue("Melaksanakan asesmen psikologis" in detail["deskripsi"])
        self.assertTrue("Psikologi" in detail["syarat"])
        self.assertFalse("hari kerja per minggu" in detail["syarat"])
        self.assertEqual(detail["perusahaan_source_id"], "8116d8c3-edc4-4fe4-8018-9e31284e83eb")
        self.assertEqual(detail["tgl_buka"], "2026-07-14")
        self.assertEqual(detail["tgl_tutup"], "2026-07-28")
        self.assertIsNone(detail["kontak_email"])


if __name__ == "__main__":
    unittest.main()
