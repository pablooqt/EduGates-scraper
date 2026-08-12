import unittest
import os
import shutil
import tempfile
from src.csv_store import CSVStore, CSV_SCHEMA_COLUMNS


class TestCSVStore(unittest.TestCase):

    def setUp(self):
        self.test_dir = tempfile.mkdtemp()
        self.csv_path = os.path.join(self.test_dir, "lowongan_magang.csv")
        self.store = CSVStore(file_path=self.csv_path, backup_enabled=True)

    def tearDown(self):
        shutil.rmtree(self.test_dir)

    def test_save_and_load(self):
        records = [{
            "source": "maganghub",
            "source_id": "uuid-101",
            "source_url": "https://maganghub.kemnaker.go.id/lowongan/test-101",
            "perusahaan_source_id": "co-101",
            "perusahaan_nama": "PT Alpha",
            "perusahaan_id": "maganghub-co-101",
            "judul": "Data Analyst Intern",
            "slug": "data-analyst-intern-uuid-101",
            "deskripsi": "Analyze data",
            "lokasi": "Jakarta",
            "durasi": None,
            "kuota": 3,
            "status": "Aktif",
            "tgl_buka": None,
            "tgl_tutup": None,
            "syarat": "Python SQL",
            "kontak_email": None,
            "scraped_at": "2026-08-11T09:00:00Z"
        }]

        success = self.store.save_dataset(records)
        self.assertTrue(success)
        self.assertTrue(os.path.exists(self.csv_path))

        loaded = self.store.load_existing()
        self.assertEqual(len(loaded), 1)
        self.assertEqual(loaded[0]["source"], "maganghub")
        self.assertEqual(loaded[0]["source_id"], "uuid-101")
        self.assertEqual(loaded[0]["judul"], "Data Analyst Intern")

        self.assertEqual(list(loaded[0].keys()), CSV_SCHEMA_COLUMNS)

    def test_backup_creation(self):
        records = [{"source": "maganghub", "source_id": f"uuid-{i}", "judul": f"Job {i}"} for i in range(10)]
        self.store.save_dataset(records)

        records_updated = [{"source": "maganghub", "source_id": f"uuid-{i}", "judul": f"Job {i} updated"} for i in range(10)]
        self.store.save_dataset(records_updated)

        backup_dir = os.path.join(self.test_dir, "backups")
        self.assertTrue(os.path.exists(backup_dir))
        backups = os.listdir(backup_dir)
        self.assertGreaterEqual(len(backups), 1)


if __name__ == "__main__":
    unittest.main()
