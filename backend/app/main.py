from __future__ import annotations

import json
import re
from typing import Any

from fastapi import FastAPI, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from .database import PROJECT_ROOT, connect, health_check, init_db, rows_to_dicts
from .fetchers import FetchedItem, fetch_source_items
from .timezone import now_shanghai_text


app = FastAPI(title="Info Flow Hub", version="0.1.0")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST", "PATCH"],
    allow_headers=["*"],
)

STATIC_DIR = PROJECT_ROOT / "dist"
INDEX_HTML = STATIC_DIR / "index.html"


class SourceIn(BaseModel):
    name: str
    fetcher_type: str
    config: dict[str, Any]
    enabled: bool = True
    fetch_interval_minutes: int = 15


class SourcePatchIn(BaseModel):
    name: str | None = None
    config: dict[str, Any] | None = None
    enabled: bool | None = None
    fetch_interval_minutes: int | None = None


class FilterRuleIn(BaseModel):
    source_id: int | None = None
    field: str
    match_type: str
    pattern: str
    action: str = "hide"
    enabled: bool = True


def decode_json(value: str | None) -> Any:
    if not value:
        return None
    try:
        return json.loads(value)
    except json.JSONDecodeError:
        return value


def source_row_to_dict(row) -> dict[str, Any]:
    item = dict(row)
    item["config"] = decode_json(item.get("config")) or {}
    item["enabled"] = bool(item["enabled"])
    return item


def item_row_to_dict(row) -> dict[str, Any]:
    item = dict(row)
    item["metadata"] = decode_json(item.get("metadata")) or {}
    item["hidden"] = bool(item["hidden"])
    return item


def rule_row_to_dict(row) -> dict[str, Any]:
    item = dict(row)
    item["enabled"] = bool(item["enabled"])
    return item


def validate_source(payload: SourceIn | SourcePatchIn) -> None:
    fetcher_type = getattr(payload, "fetcher_type", None)
    if fetcher_type and fetcher_type not in {"rss", "http_scrape", "cdp_browser"}:
        raise HTTPException(status_code=422, detail="fetcher_type must be rss, http_scrape, or cdp_browser")
    interval = getattr(payload, "fetch_interval_minutes", None)
    if interval is not None and interval < 1:
        raise HTTPException(status_code=422, detail="fetch_interval_minutes must be positive")


def validate_rule(payload: FilterRuleIn) -> None:
    if payload.field not in {"title", "content", "author"}:
        raise HTTPException(status_code=422, detail="field must be title, content, or author")
    if payload.match_type not in {"contains", "regex"}:
        raise HTTPException(status_code=422, detail="match_type must be contains or regex")
    if payload.action != "hide":
        raise HTTPException(status_code=422, detail="only hide action is supported")
    if payload.match_type == "regex":
        try:
            re.compile(payload.pattern)
        except re.error as exc:
            raise HTTPException(status_code=422, detail=f"invalid regex: {exc}") from exc


def matches_rule(value: str | None, rule: dict[str, Any]) -> bool:
    text = value or ""
    if rule["match_type"] == "contains":
        return rule["pattern"].lower() in text.lower()
    return re.search(rule["pattern"], text) is not None


def apply_filters_for_item(conn, item_id: int) -> bool:
    item = conn.execute("SELECT * FROM items WHERE id = ?", (item_id,)).fetchone()
    if not item:
        return False
    rules = rows_to_dicts(
        conn.execute(
            """
            SELECT * FROM filter_rules
            WHERE enabled = 1 AND (source_id IS NULL OR source_id = ?)
            ORDER BY id
            """,
            (item["source_id"],),
        ).fetchall()
    )
    for rule in rules:
        if matches_rule(item[rule["field"]], rule):
            conn.execute("UPDATE items SET hidden = 1 WHERE id = ?", (item_id,))
            return not bool(item["hidden"])
    return False


def apply_filters(conn, source_id: int | None = None) -> int:
    if source_id:
        rows = conn.execute("SELECT id FROM items WHERE source_id = ?", (source_id,)).fetchall()
    else:
        rows = conn.execute("SELECT id FROM items").fetchall()
    hidden = 0
    for row in rows:
        if apply_filters_for_item(conn, row["id"]):
            hidden += 1
    return hidden


def upsert_item(conn, source_id: int, fetched: FetchedItem) -> tuple[bool, int]:
    now = now_shanghai_text()
    metadata = json.dumps(fetched.metadata or {}, ensure_ascii=False)
    cursor = conn.execute(
        """
        INSERT INTO items
          (source_id, source_item_id, title, url, content, author, published_at, fetched_at, metadata)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(source_id, source_item_id) DO UPDATE SET
          title = excluded.title,
          url = excluded.url,
          content = excluded.content,
          author = excluded.author,
          published_at = excluded.published_at,
          fetched_at = excluded.fetched_at,
          metadata = excluded.metadata
        """,
        (
            source_id,
            fetched.source_item_id,
            fetched.title,
            fetched.url,
            fetched.content,
            fetched.author,
            fetched.published_at,
            now,
            metadata,
        ),
    )
    row = conn.execute(
        "SELECT id FROM items WHERE source_id = ? AND source_item_id = ?",
        (source_id, fetched.source_item_id),
    ).fetchone()
    return cursor.rowcount == 1, int(row["id"])


def run_fetch(source_id: int) -> dict[str, Any]:
    with connect() as conn:
        source = conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
        if not source:
            raise HTTPException(status_code=404, detail="source not found")
        config = decode_json(source["config"]) or {}
        fetched_items = fetch_source_items(source["fetcher_type"], config)
        imported = 0
        updated = 0
        hidden = 0
        for fetched in fetched_items:
            inserted, item_id = upsert_item(conn, source_id, fetched)
            if inserted:
                imported += 1
            else:
                updated += 1
            if apply_filters_for_item(conn, item_id):
                hidden += 1
        conn.execute(
            "UPDATE sources SET last_fetched_at = ? WHERE id = ?",
            (now_shanghai_text(), source_id),
        )
    return {
        "ok": True,
        "source_id": source_id,
        "fetched": len(fetched_items),
        "imported": imported,
        "updated": updated,
        "hidden": hidden,
    }


@app.on_event("startup")
def startup() -> None:
    init_db()


@app.get("/api/health")
def health():
    return {"ok": True, "service": "info-flow-hub", "version": "0.1.0", **health_check()}


@app.get("/api/items")
def get_items(
    source_id: int | None = None,
    limit: int = Query(50, ge=1, le=200),
    before: str | None = None,
    include_hidden: bool = False,
):
    where = []
    params: list[Any] = []
    if source_id is not None:
        where.append("items.source_id = ?")
        params.append(source_id)
    if before:
        where.append("COALESCE(items.published_at, items.fetched_at) < ?")
        params.append(before)
    if not include_hidden:
        where.append("items.hidden = 0")
    clause = "WHERE " + " AND ".join(where) if where else ""
    params.append(limit)
    with connect() as conn:
        rows = conn.execute(
            f"""
            SELECT items.*, sources.name AS source_name, sources.fetcher_type AS fetcher_type
            FROM items JOIN sources ON sources.id = items.source_id
            {clause}
            ORDER BY COALESCE(items.published_at, items.fetched_at) DESC, items.id DESC
            LIMIT ?
            """,
            params,
        ).fetchall()
    return {"ok": True, "count": len(rows), "items": [item_row_to_dict(row) for row in rows]}


@app.get("/api/sources")
def get_sources():
    with connect() as conn:
        rows = conn.execute(
            """
            SELECT sources.*,
              COUNT(items.id) AS item_count,
              SUM(CASE WHEN items.hidden = 1 THEN 1 ELSE 0 END) AS hidden_count
            FROM sources
            LEFT JOIN items ON items.source_id = sources.id
            GROUP BY sources.id
            ORDER BY sources.id
            """
        ).fetchall()
    return {"ok": True, "sources": [source_row_to_dict(row) for row in rows]}


@app.post("/api/sources", status_code=201)
def post_source(payload: SourceIn):
    validate_source(payload)
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO sources
              (name, fetcher_type, config, enabled, fetch_interval_minutes, created_at)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                payload.name,
                payload.fetcher_type,
                json.dumps(payload.config, ensure_ascii=False),
                int(payload.enabled),
                payload.fetch_interval_minutes,
                now_shanghai_text(),
            ),
        )
        row = conn.execute("SELECT * FROM sources WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return {"ok": True, "source": source_row_to_dict(row)}


@app.patch("/api/sources/{source_id}")
def patch_source(source_id: int, payload: SourcePatchIn):
    validate_source(payload)
    updates = payload.model_dump(exclude_unset=True)
    if not updates:
        raise HTTPException(status_code=400, detail="empty patch")
    if "config" in updates:
        updates["config"] = json.dumps(updates["config"], ensure_ascii=False)
    if "enabled" in updates:
        updates["enabled"] = int(updates["enabled"])
    columns = ", ".join(f"{key} = ?" for key in updates)
    values = list(updates.values()) + [source_id]
    with connect() as conn:
        conn.execute(f"UPDATE sources SET {columns} WHERE id = ?", values)
        row = conn.execute("SELECT * FROM sources WHERE id = ?", (source_id,)).fetchone()
    if not row:
        raise HTTPException(status_code=404, detail="source not found")
    return {"ok": True, "source": source_row_to_dict(row)}


@app.get("/api/filter-rules")
def get_filter_rules():
    with connect() as conn:
        rows = conn.execute("SELECT * FROM filter_rules ORDER BY id DESC").fetchall()
    return {"ok": True, "rules": [rule_row_to_dict(row) for row in rows]}


@app.post("/api/filter-rules", status_code=201)
def post_filter_rule(payload: FilterRuleIn):
    validate_rule(payload)
    with connect() as conn:
        cursor = conn.execute(
            """
            INSERT INTO filter_rules
              (source_id, field, match_type, pattern, action, enabled, created_at)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                payload.source_id,
                payload.field,
                payload.match_type,
                payload.pattern,
                payload.action,
                int(payload.enabled),
                now_shanghai_text(),
            ),
        )
        hidden = apply_filters(conn, payload.source_id)
        row = conn.execute("SELECT * FROM filter_rules WHERE id = ?", (cursor.lastrowid,)).fetchone()
    return {"ok": True, "rule": rule_row_to_dict(row), "hidden": hidden}


@app.post("/api/filter-rules/apply")
def post_apply_filter_rules(source_id: int | None = None):
    with connect() as conn:
        hidden = apply_filters(conn, source_id)
    return {"ok": True, "hidden": hidden}


@app.post("/api/fetch/{source_id}")
def post_fetch(source_id: int):
    return run_fetch(source_id)


if STATIC_DIR.exists():
    app.mount("/assets", StaticFiles(directory=STATIC_DIR / "assets"), name="assets")


@app.get("/{path:path}", include_in_schema=False)
def spa_fallback(path: str):
    target = STATIC_DIR / path
    if target.is_file():
        return FileResponse(target)
    if INDEX_HTML.exists():
        return FileResponse(INDEX_HTML)
    return Response("Info Flow Hub frontend has not been built yet.", media_type="text/plain")
