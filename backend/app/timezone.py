from __future__ import annotations

from datetime import datetime, timezone
from zoneinfo import ZoneInfo


SHANGHAI = ZoneInfo("Asia/Shanghai")


def now_shanghai() -> datetime:
    return datetime.now(SHANGHAI)


def now_shanghai_text() -> str:
    return now_shanghai().replace(microsecond=0).isoformat()


def utc_now_text() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()
