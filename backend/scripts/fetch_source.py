#!/usr/bin/env python3
from __future__ import annotations

from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "backend"))

from app.database import init_db
from app.main import run_fetch


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: fetch_source.py SOURCE_ID", file=sys.stderr)
        return 2
    init_db()
    print(run_fetch(int(sys.argv[1])))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
