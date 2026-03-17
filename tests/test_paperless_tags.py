import sys
import types
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.append(str(Path(__file__).resolve().parents[1] / "src"))
sys.modules.setdefault("chromadb", types.SimpleNamespace(PersistentClient=object))
sys.modules.setdefault(
    "frontmatter",
    types.SimpleNamespace(load=lambda *a, **k: None, loads=lambda *a, **k: types.SimpleNamespace(metadata={})),
)

from rag_api import indexer as indexer_module  # noqa: E402
from rag_api.indexer import _with_paperless_metadata_text, _paperless_tag_names  # noqa: E402


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

    def test_failed_tag_lookup_is_not_cached_permanently(self):
        class _Resp:
            def __init__(self, ok: bool, name: str = ""):
                self.ok = ok
                self._name = name

            def json(self):
                return {"name": self._name}

        indexer_module._PAPERLESS_TAG_NAME_CACHE.clear()

        with patch("requests.get", side_effect=[_Resp(False), _Resp(True, "rechnung")]) as mocked_get:
            first = _paperless_tag_names([123], "https://paperless.local", "token")
            second = _paperless_tag_names([123], "https://paperless.local", "token")

        self.assertEqual(first, [])
        self.assertEqual(second, ["rechnung"])
        self.assertEqual(mocked_get.call_count, 2)


if __name__ == "__main__":
    unittest.main()
