from __future__ import annotations

import os

import uvicorn


def selected_port() -> int:
    raw = os.environ.get("PORT", "8030")
    try:
        port = int(raw)
    except ValueError as exc:
        raise RuntimeError(f"invalid PORT value {raw!r}: expected integer 1-65535") from exc
    if port < 1 or port > 65535:
        raise RuntimeError(f"invalid PORT value {raw!r}: expected integer 1-65535")
    return port


if __name__ == "__main__":
    uvicorn.run("app.main:app", host="0.0.0.0", port=selected_port(), reload=False)
