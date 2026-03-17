import unittest
from unittest.mock import patch

from rag_api import indexer as indexer_module
from rag_api.indexer import _with_paperless_metadata_text, _paperless_tag_names, _paperless_correspondent_name


class TestPaperlessMetadataText(unittest.TestCase):
    def test_includes_tag_names_in_prefixed_content(self):
        content = "invoice content"
        meta = {
            "title": "Stromrechnung",
            "correspondent": "Energie AG",
            "tag_names": "rechnung, strom, 2026",
        }

        enriched = _with_paperless_metadata_text(content, meta)

        self.assertIn("Paperless Metadata", enriched)
        self.assertIn("Title: Stromrechnung", enriched)
        self.assertIn("Correspondent: Energie AG", enriched)
        self.assertIn("Tags: rechnung, strom, 2026", enriched)
        self.assertTrue(enriched.endswith("invoice content"))

    def test_returns_original_content_without_metadata(self):
        content = "plain page text"
        self.assertEqual(_with_paperless_metadata_text(content, {}), content)

    def test_tags_are_repeated_for_embedding_weight(self):
        enriched = _with_paperless_metadata_text("body", {"tag_names": "etron"})
        self.assertEqual(enriched.count("Tags: etron"), 5)

    def test_failed_tag_lookup_is_not_cached_permanently(self):
        class _Resp:
            def __init__(self, ok: bool, data=None):
                self.ok = ok
                self._data = data or {}

            def json(self):
                return self._data

        indexer_module._PAPERLESS_TAG_NAME_CACHE.clear()

        # First call: batch returns failure, individual fallback also fails
        # Second call: batch returns the tag successfully
        with patch("requests.get", side_effect=[
            _Resp(False),              # 1st batch attempt fails
            _Resp(False),              # 1st individual fallback fails
            _Resp(True, {"results": [{"id": 123, "name": "rechnung"}]}),  # 2nd batch succeeds
        ]) as mocked_get:
            first = _paperless_tag_names([123], "https://paperless.local", "token")
            second = _paperless_tag_names([123], "https://paperless.local", "token")

        self.assertEqual(first, [])
        self.assertEqual(second, ["rechnung"])
        self.assertEqual(mocked_get.call_count, 3)


if __name__ == "__main__":
    unittest.main()
