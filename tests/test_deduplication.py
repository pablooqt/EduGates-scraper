import unittest
from src.deduplicator import VacancyDeduplicator


class TestDeduplicator(unittest.TestCase):

    def test_insert_new_record(self):
        dedup = VacancyDeduplicator()
        raw = {
            "source": "maganghub",
            "source_id": "uuid-001",
            "source_url": "https://maganghub.kemnaker.go.id/lowongan/test-uuid-001",
            "judul": "Software Engineer Intern",
            "perusahaan_nama": "PT Tech Solutions",
            "kuota": 5
        }
        action, norm = dedup.process_record(raw)
        self.assertEqual(action, "inserted")
        self.assertEqual(norm["source"], "maganghub")
        self.assertEqual(norm["source_id"], "uuid-001")
        self.assertEqual(norm["judul"], "Software Engineer Intern")
        self.assertEqual(norm["perusahaan_id"], "maganghub-company-dc18237b")
        self.assertEqual(len(dedup.get_all_records()), 1)

    def test_unchanged_record(self):
        existing = [{
            "source": "maganghub",
            "source_id": "uuid-001",
            "source_url": "https://maganghub.kemnaker.go.id/lowongan/test-uuid-001",
            "judul": "Software Engineer Intern",
            "perusahaan_nama": "PT Tech Solutions",
            "kuota": 5,
            "status": "Aktif"
        }]
        dedup = VacancyDeduplicator(existing)

        raw = {
            "source": "maganghub",
            "source_id": "uuid-001",
            "source_url": "https://maganghub.kemnaker.go.id/lowongan/test-uuid-001",
            "judul": "Software Engineer Intern",
            "perusahaan_nama": "PT Tech Solutions",
            "kuota": 5,
            "status": "Aktif"
        }
        action, norm = dedup.process_record(raw)
        self.assertEqual(action, "unchanged")
        self.assertEqual(len(dedup.get_all_records()), 1)

    def test_updated_record(self):
        existing = [{
            "source": "maganghub",
            "source_id": "uuid-001",
            "source_url": "https://maganghub.kemnaker.go.id/lowongan/test-uuid-001",
            "judul": "Software Engineer Intern",
            "perusahaan_nama": "PT Tech Solutions",
            "kuota": 5,
            "status": "Aktif"
        }]
        dedup = VacancyDeduplicator(existing)

        raw = {
            "source": "maganghub",
            "source_id": "uuid-001",
            "source_url": "https://maganghub.kemnaker.go.id/lowongan/test-uuid-001",
            "judul": "Software Engineer Intern",
            "perusahaan_nama": "PT Tech Solutions",
            "kuota": 10,
            "status": "Aktif"
        }
        action, norm = dedup.process_record(raw)
        self.assertEqual(action, "updated")
        self.assertEqual(norm["kuota"], 10)
        self.assertEqual(len(dedup.get_all_records()), 1)


if __name__ == "__main__":
    unittest.main()
