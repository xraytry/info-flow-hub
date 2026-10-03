from __future__ import annotations

import hashlib
import json
import os
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass
from typing import Any

import feedparser
import httpx
from bs4 import BeautifulSoup
from websocket import create_connection


@dataclass
class FetchedItem:
    source_item_id: str
    title: str | None = None
    url: str | None = None
    content: str | None = None
    author: str | None = None
    published_at: str | None = None
    metadata: dict[str, Any] | None = None


def stable_id(*parts: str | None) -> str:
    raw = "|".join(part or "" for part in parts)
    return hashlib.sha256(raw.encode("utf-8")).hexdigest()


def strip_text(value: Any) -> str | None:
    if value is None:
        return None
    text = re.sub(r"\s+", " ", str(value)).strip()
    return text or None


def fetch_rss(config: dict[str, Any]) -> list[FetchedItem]:
    feed_url = config.get("feed_url")
    if not feed_url:
        raise ValueError("rss config requires feed_url")
    parsed = feedparser.parse(config.get("feed_xml") or feed_url)
    items: list[FetchedItem] = []
    for entry in parsed.entries:
        link = entry.get("link")
        guid = entry.get("id") or entry.get("guid") or link
        title = strip_text(entry.get("title"))
        content = strip_text(
            entry.get("summary")
            or (entry.get("content") or [{}])[0].get("value")
            if entry.get("content")
            else entry.get("summary")
        )
        published = entry.get("published") or entry.get("updated")
        items.append(
            FetchedItem(
                source_item_id=str(guid or stable_id(title, link, published)),
                title=title,
                url=link,
                content=content,
                author=strip_text(entry.get("author")),
                published_at=published,
                metadata={"feed_url": feed_url},
            )
        )
    return items


def select_text(base, selector: str | None) -> str | None:
    if not selector:
        return None
    node = base.select_one(selector)
    return strip_text(node.get_text(" ", strip=True)) if node else None


def select_href(base, selector: str | None, root_url: str) -> str | None:
    if not selector:
        return None
    node = base.select_one(selector)
    href = node.get("href") if node else None
    return urllib.parse.urljoin(root_url, href) if href else None


def fetch_http_scrape(config: dict[str, Any]) -> list[FetchedItem]:
    list_url = config.get("list_url")
    item_selector = config.get("item_selector")
    if not list_url or not item_selector:
        raise ValueError("http_scrape config requires list_url and item_selector")
    response = httpx.get(list_url, timeout=20, follow_redirects=True)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "html.parser")
    items = []
    for node in soup.select(item_selector):
        title = select_text(node, config.get("title_selector"))
        url = select_href(node, config.get("link_selector"), list_url)
        content = select_text(node, config.get("content_selector"))
        published = select_text(node, config.get("date_selector"))
        author = select_text(node, config.get("author_selector"))
        items.append(
            FetchedItem(
                source_item_id=url or stable_id(title, content, published),
                title=title,
                url=url,
                content=content,
                author=author,
                published_at=published,
                metadata={"list_url": list_url},
            )
        )
    return items


def cdp_default_extract_js(config: dict[str, Any]) -> str:
    item_selector = json.dumps(config.get("item_selector") or "article")
    title_selector = json.dumps(config.get("title_selector") or "")
    link_selector = json.dumps(config.get("link_selector") or "a[href*='/status/']")
    author_selector = json.dumps(config.get("author_selector") or "")
    date_selector = json.dumps(config.get("date_selector") or "time")
    return f"""
(() => {{
  const text = (node) => node ? node.textContent.replace(/\\s+/g, ' ').trim() : null;
  const attr = (node, name) => node ? node.getAttribute(name) : null;
  return Array.from(document.querySelectorAll({item_selector})).slice(0, 50).map((item) => {{
    const titleNode = {title_selector} ? item.querySelector({title_selector}) : item;
    const linkNode = item.querySelector({link_selector});
    const authorNode = {author_selector} ? item.querySelector({author_selector}) : null;
    const dateNode = {date_selector} ? item.querySelector({date_selector}) : null;
    const href = attr(linkNode, 'href');
    return {{
      title: text(titleNode),
      url: href ? new URL(href, location.href).toString() : null,
      content: text(item),
      author: text(authorNode),
      published_at: attr(dateNode, 'datetime') || text(dateNode),
      source_item_id: href || text(titleNode)
    }};
  }}).filter((item) => item.source_item_id || item.url || item.title);
}})()
"""


def parse_cdp_runtime_result(payload: dict[str, Any]) -> list[FetchedItem]:
    value = payload.get("result", {}).get("result", {}).get("value")
    if isinstance(value, str):
        value = json.loads(value)
    if not isinstance(value, list):
        raise ValueError("CDP Runtime.evaluate did not return an item list")
    items = []
    for raw in value:
        if not isinstance(raw, dict):
            continue
        title = strip_text(raw.get("title"))
        url = raw.get("url")
        source_item_id = raw.get("source_item_id") or url or stable_id(title, raw.get("content"))
        items.append(
            FetchedItem(
                source_item_id=str(source_item_id),
                title=title,
                url=url,
                content=strip_text(raw.get("content")),
                author=strip_text(raw.get("author")),
                published_at=strip_text(raw.get("published_at")),
                metadata={"cdp": True},
            )
        )
    return items


def cdp_request(ws, method: str, params: dict[str, Any] | None = None, request_id: int = 1) -> dict[str, Any]:
    ws.send(json.dumps({"id": request_id, "method": method, "params": params or {}}))
    while True:
        message = json.loads(ws.recv())
        if message.get("id") == request_id:
            return message


def fetch_cdp_browser(config: dict[str, Any]) -> list[FetchedItem]:
    target_url = config.get("url")
    if not target_url:
        raise ValueError("cdp_browser config requires url")
    cdp_url = os.environ.get("CDP_URL", "http://127.0.0.1:9222").rstrip("/")
    create_url = f"{cdp_url}/json/new?{urllib.parse.quote(target_url, safe='')}"
    with urllib.request.urlopen(urllib.request.Request(create_url, method="PUT"), timeout=10) as response:
        target = json.loads(response.read().decode("utf-8"))
    ws_url = target["webSocketDebuggerUrl"]
    ws = create_connection(ws_url, timeout=20)
    try:
        cdp_request(ws, "Page.enable", request_id=1)
        cdp_request(ws, "Runtime.enable", request_id=2)
        cdp_request(ws, "Page.navigate", {"url": target_url}, request_id=3)
        time.sleep(float(config.get("wait_seconds", 5)))
        expression = config.get("extract_js") or cdp_default_extract_js(config)
        payload = cdp_request(
            ws,
            "Runtime.evaluate",
            {"expression": expression, "returnByValue": True, "awaitPromise": True},
            request_id=4,
        )
        return parse_cdp_runtime_result(payload)
    finally:
        ws.close()
        close_url = f"{cdp_url}/json/close/{target.get('id')}"
        try:
            urllib.request.urlopen(close_url, timeout=5).read()
        except Exception:
            pass


def fetch_source_items(fetcher_type: str, config: dict[str, Any]) -> list[FetchedItem]:
    if fetcher_type == "rss":
        return fetch_rss(config)
    if fetcher_type == "http_scrape":
        return fetch_http_scrape(config)
    if fetcher_type == "cdp_browser":
        return fetch_cdp_browser(config)
    raise ValueError(f"unsupported fetcher_type: {fetcher_type}")
