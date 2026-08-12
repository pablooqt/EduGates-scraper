import unittest
from src.sources.registry import SourceRegistry
from src.sources.maganghub import MagangHubSource


class TestSourceRegistry(unittest.TestCase):

    def test_list_sources(self):
        sources = SourceRegistry.list_sources()
        self.assertIn("maganghub", sources)

    def test_get_source_success(self):
        source = SourceRegistry.get_source("maganghub")
        self.assertIsInstance(source, MagangHubSource)
        self.assertEqual(source.name, "maganghub")

    def test_get_source_case_insensitive(self):
        source = SourceRegistry.get_source("MAGANGHUB")
        self.assertIsInstance(source, MagangHubSource)

    def test_get_unknown_source_raises(self):
        with self.assertRaises(ValueError):
            SourceRegistry.get_source("non_existent_source")


if __name__ == "__main__":
    unittest.main()
