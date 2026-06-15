from __future__ import annotations

import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
DB = ROOT / "test-info-flow.db"
BASE = "http://127.0.0.1:8140"
SAMPLE_FEED = """<?xml version="1.0"?>
<rss version="2.0"><channel><title>Test</title>
<item><guid>one</guid><title>Hello Linux</title><link>https://example.com/1</link><description>Keep me</description><pubDate>Mon, 15 Jun 2026 08:00:00 +0800</pubDate></item>
<item><guid>two</guid><title>Blocked item</title><link>https://example.com/2</link><description>Hide me</description><pubDate>Mon, 15 Jun 2026 09:00:00 +0800</pubDate></item>
</channel></rss>"""


def call(method: str, path: str, body=None):
    data = None if body is None else json.dumps(body, ensure_ascii=False).encode("utf-8")
    headers = {"Content-Type": "application/json"} if data is not None else {}
    req = urllib.request.Request(BASE + path, data=data, method=method, headers=headers)
    with urllib.request.urlopen(req, timeout=8) as response:
        return response.status, json.loads(response.read().decode("utf-8"))


class ApiTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        for suffix in ("", "-shm", "-wal"):
            (ROOT / f"test-info-flow.db{suffix}").unlink(missing_ok=True)
        env = os.environ.copy()
        env["INFO_FLOW_DB"] = str(DB)
        env["PYTHONPATH"] = str(ROOT / "backend")
        cls.process = subprocess.Popen(
            [sys.executable, "-m", "uvicorn", "app.main:app", "--host", "127.0.0.1", "--port", "8140"],
            cwd=ROOT / "backend",
            env=env,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.STDOUT,
        )
        for _ in range(50):
            try:
                if call("GET", "/api/health")[1]["ok"]:
                    return
            except Exception:
                time.sleep(0.2)
        raise RuntimeError("server did not become ready")

    @classmethod
    def tearDownClass(cls):
        cls.process.terminate()
        cls.process.wait(timeout=5)
        for suffix in ("", "-shm", "-wal"):
            (ROOT / f"test-info-flow.db{suffix}").unlink(missing_ok=True)

    def test_rss_fetch_idempotent_and_filter_rules_hide_items(self):
        status, source = call("POST", "/api/sources", {
            "name": "mock-rss",
            "fetcher_type": "rss",
            "config": {"feed_url": "mock://feed", "feed_xml": SAMPLE_FEED},
        })
        self.assertEqual(status, 201)
        source_id = source["source"]["id"]

        first = call("POST", f"/api/fetch/{source_id}")[1]
        second = call("POST", f"/api/fetch/{source_id}")[1]
        self.assertEqual(first["fetched"], 2)
        self.assertEqual(second["fetched"], 2)

        items = call("GET", "/api/items?limit=10")[1]["items"]
        self.assertEqual(len(items), 2)

        rule = call("POST", "/api/filter-rules", {
            "field": "title",
            "match_type": "contains",
            "pattern": "Blocked",
        })[1]
        self.assertEqual(rule["hidden"], 1)
        visible = call("GET", "/api/items?limit=10")[1]["items"]
        self.assertEqual(len(visible), 1)
        self.assertEqual(visible[0]["title"], "Hello Linux")

        regex_rule = call("POST", "/api/filter-rules", {
            "field": "content",
            "match_type": "regex",
            "pattern": "Keep\\s+me",
        })[1]
        self.assertEqual(regex_rule["hidden"], 1)
        empty = call("GET", "/api/items?limit=10")[1]["items"]
        self.assertEqual(empty, [])

    def test_http_scrape_source_can_be_created(self):
        status, source = call("POST", "/api/sources", {
            "name": "static-placeholder",
            "fetcher_type": "http_scrape",
            "config": {"list_url": "https://example.com", "item_selector": "article"},
            "enabled": False,
        })
        self.assertEqual(status, 201)
        self.assertEqual(source["source"]["fetcher_type"], "http_scrape")


if __name__ == "__main__":
    unittest.main()
