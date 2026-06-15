-- info-flow-hub schema v1
-- FastAPI + SQLite single deployable app.

CREATE TABLE IF NOT EXISTS sources (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  name          TEXT NOT NULL,
  fetcher_type  TEXT NOT NULL CHECK (fetcher_type IN ('rss', 'http_scrape', 'cdp_browser')),
  config        TEXT NOT NULL,
  enabled       INTEGER NOT NULL DEFAULT 1,
  fetch_interval_minutes INTEGER NOT NULL DEFAULT 15,
  last_fetched_at TEXT,
  created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_sources_enabled ON sources(enabled);

CREATE TABLE IF NOT EXISTS items (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  source_id     INTEGER NOT NULL REFERENCES sources(id) ON DELETE CASCADE,
  source_item_id TEXT NOT NULL,
  title         TEXT,
  url           TEXT,
  content       TEXT,
  author        TEXT,
  published_at  TEXT,
  fetched_at    TEXT NOT NULL,
  hidden        INTEGER NOT NULL DEFAULT 0,
  metadata      TEXT,
  UNIQUE(source_id, source_item_id)
);
CREATE INDEX IF NOT EXISTS idx_items_published ON items(published_at DESC);
CREATE INDEX IF NOT EXISTS idx_items_source ON items(source_id);
CREATE INDEX IF NOT EXISTS idx_items_hidden ON items(hidden);

CREATE TABLE IF NOT EXISTS filter_rules (
  id            INTEGER PRIMARY KEY AUTOINCREMENT,
  source_id     INTEGER REFERENCES sources(id) ON DELETE CASCADE,
  field         TEXT NOT NULL CHECK (field IN ('title', 'content', 'author')),
  match_type    TEXT NOT NULL CHECK (match_type IN ('contains', 'regex')),
  pattern       TEXT NOT NULL,
  action        TEXT NOT NULL DEFAULT 'hide' CHECK (action IN ('hide')),
  enabled       INTEGER NOT NULL DEFAULT 1,
  created_at    TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_filter_rules_source ON filter_rules(source_id);
CREATE INDEX IF NOT EXISTS idx_filter_rules_enabled ON filter_rules(enabled);
