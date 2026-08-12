import unittest
from src.normalizer import (
    normalize_text,
    normalize_quota,
    normalize_status,
    normalize_date,
    normalize_slug,
    sanitize_csv_cell
)


class TestNormalizer(unittest.TestCase):

    def test_normalize_text(self):
        raw = "  Hello World \r\n  Line 2  \n\n  "
        self.assertEqual(normalize_text(raw), "Hello World | Line 2")

    def test_normalize_quota(self):
        self.assertEqual(normalize_quota("10 peserta"), 10)
        self.assertEqual(normalize_quota("Kuota: 5"), 5)
        self.assertEqual(normalize_quota("15 orang"), 15)
        self.assertEqual(normalize_quota(20), 20)
        self.assertIsNone(normalize_quota("Terbatas"))
        self.assertIsNone(normalize_quota(None))

    def test_normalize_status(self):
        self.assertEqual(normalize_status("Aktif"), "Aktif")
        self.assertEqual(normalize_status("Buka"), "Aktif")
        self.assertEqual(normalize_status("Tutup"), "Tutup")
        self.assertEqual(normalize_status("Closed"), "Tutup")
        self.assertEqual(normalize_status("Ditutup"), "Tutup")

    def test_normalize_date(self):
        self.assertEqual(normalize_date("15 Agustus 2026"), "2026-08-15")
        self.assertEqual(normalize_date("1 Januari 2025"), "2025-01-01")
        self.assertEqual(normalize_date("2026-12-31"), "2026-12-31")
        self.assertIsNone(normalize_date("invalid date"))

    def test_normalize_slug(self):
        self.assertEqual(normalize_slug("Software Engineer", "12345"), "software-engineer-12345")
        self.assertEqual(normalize_slug("Frontend Dev", "12345", "frontend-developer"), "frontend-developer-12345")

    def test_sanitize_csv_cell(self):
        self.assertEqual(sanitize_csv_cell("=1+1"), "'=1+1")
        self.assertEqual(sanitize_csv_cell("+cmd"), "'+cmd")
        self.assertEqual(sanitize_csv_cell("-sub"), "'-sub")
        self.assertEqual(sanitize_csv_cell("@eval"), "'@eval")
        self.assertEqual(sanitize_csv_cell("Normal Text"), "Normal Text")


if __name__ == "__main__":
    unittest.main()
