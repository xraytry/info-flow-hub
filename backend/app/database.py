from __future__ import annotations

import os
import sqlite3
from pathlib import Path
from typing import Any, Iterable


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_DB_PATH = PROJECT_ROOT / "info_flow_hub.db"
SCHEMA_PATH = Path(__file__).resolve().parents[1] / "schema.sql"


def db_path() -> Path:
    return Path(os.environ.get("INFO_FLOW_DB", str(DEFAULT_DB_PATH)))


def connect() -> sqlite3.Connection:
    path = db_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA journal_mode = WAL")
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 5000")
    conn.execute("PRAGMA synchronous = NORMAL")
    return conn


def init_db() -> None:
    with connect() as conn:
        conn.executescript(SCHEMA_PATH.read_text(encoding="utf-8"))


def rows_to_dicts(rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
    return [dict(row) for row in rows]


def health_check() -> dict[str, Any]:
    expected = {"sources", "items", "filter_rules"}
    with connect() as conn:
        rows = conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()
        actual = {row["name"] for row in rows}
    missing = sorted(expected - actual)
    return {
        "ok": not missing,
        "db_path": str(db_path()),
        "tables": sorted(actual & expected),
        "missing": missing,
    }
