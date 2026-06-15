from __future__ import annotations

import unittest

from backend.app.fetchers import cdp_default_extract_js, parse_cdp_runtime_result


class CdpFetcherTest(unittest.TestCase):
    def test_runtime_evaluate_payload_maps_to_items(self):
        payload = {
            "result": {
                "result": {
                    "value": [
                        {
                            "source_item_id": "https://x.com/a/status/1",
                            "title": "first post",
                            "url": "https://x.com/a/status/1",
                            "content": "first post body",
                            "author": "alice",
                            "published_at": "2026-06-15T12:00:00Z",
                        }
                    ]
                }
            }
        }
        items = parse_cdp_runtime_result(payload)
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].source_item_id, "https://x.com/a/status/1")
        self.assertEqual(items[0].author, "alice")

    def test_default_extract_script_uses_config_selectors(self):
        script = cdp_default_extract_js({
            "item_selector": "article",
            "link_selector": "a[href*='/status/']",
        })
        self.assertIn("document.querySelectorAll", script)
        self.assertIn("/status/", script)


if __name__ == "__main__":
    unittest.main()
