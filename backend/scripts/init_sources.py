#!/usr/bin/env python3
from __future__ import annotations

import json
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.database import connect, init_db
from app.timezone import now_shanghai_text


DEFAULT_SOURCES = [
    {
        "name": "linux.do",
        "fetcher_type": "rss",
        "config": {"feed_url": "https://linux.do/latest.rss"},
        "fetch_interval_minutes": 15,
    },
    {
        "name": "nodeseek",
        "fetcher_type": "rss",
        "config": {"feed_url": "https://www.nodeseek.com/rss.xml"},
        "fetch_interval_minutes": 15,
    },
    {
        "name": "x.com:home",
        "fetcher_type": "cdp_browser",
        "config": {
            "url": "https://x.com/home",
            "item_selector": "article",
            "link_selector": "a[href*='/status/']",
            "wait_seconds": 5,
        },
        "fetch_interval_minutes": 15,
    },
]


def main() -> int:
    init_db()
    with connect() as conn:
        for source in DEFAULT_SOURCES:
            existing = conn.execute("SELECT id FROM sources WHERE name = ?", (source["name"],)).fetchone()
            if existing:
                continue
            conn.execute(
                """
                INSERT INTO sources
                  (name, fetcher_type, config, enabled, fetch_interval_minutes, created_at)
                VALUES (?, ?, ?, 1, ?, ?)
                """,
                (
                    source["name"],
                    source["fetcher_type"],
                    json.dumps(source["config"], ensure_ascii=False),
                    source["fetch_interval_minutes"],
                    now_shanghai_text(),
                ),
            )
    print("default sources initialized")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
