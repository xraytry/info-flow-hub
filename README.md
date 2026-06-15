# Info Flow Hub

自托管信息流聚合平台：RSS、静态页面抓取、CDP 浏览器抓取统一写入 SQLite，并通过同一套 REST API 提供给 Web UI、Hermes 或 CLI。

## Stack

- Backend: Python + FastAPI + SQLite
- Frontend: Vue3 + Vite
- Fetchers: `rss`, `http_scrape`, `cdp_browser`
- Deploy: systemd user service
- Timezone: Asia/Shanghai

本项目不使用 LazyCat / LPK / `lzc-*`。

## Local Run

```bash
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
npm install
npm run build
INFO_FLOW_DB=./info_flow_hub.db PORT=8030 .venv/bin/python backend/run.py
```

初始化默认来源：

```bash
INFO_FLOW_DB=./info_flow_hub.db .venv/bin/python backend/scripts/init_sources.py
```

手动抓取：

```bash
INFO_FLOW_DB=./info_flow_hub.db .venv/bin/python backend/scripts/fetch_source.py 1
```

## API

- `GET /api/health`
- `GET /api/items?source_id=&limit=&before=&include_hidden=`
- `GET /api/sources`
- `POST /api/sources`
- `PATCH /api/sources/{id}`
- `GET /api/filter-rules`
- `POST /api/filter-rules`
- `POST /api/filter-rules/apply`
- `POST /api/fetch/{source_id}`

## Default Sources

`backend/scripts/init_sources.py` creates:

- `linux.do`: `https://linux.do/latest.rss`
- `nodeseek`: `https://www.nodeseek.com/rss.xml`
- `x.com:home`: CDP browser placeholder for openclawonly integration testing

## CDP Browser

`cdp_browser` uses `CDP_URL`, defaulting to:

```bash
CDP_URL=http://127.0.0.1:9222
```

Mac Phase 1 tests use mock CDP payloads only. Real x.com session extraction should be verified on openclawonly where Chrome CDP is available.

## Tests

```bash
.venv/bin/python -m compileall backend
.venv/bin/python -m unittest discover -s backend/tests -v
npm run build
```

## Deploy

Recommended openclawonly path:

```bash
cd /home/lhb/info-flow-hub
INFO_FLOW_DB=/home/lhb/info-flow-hub/info_flow_hub.db PORT=8030 .venv/bin/python backend/run.py
```

systemd user service template:

```bash
cp deploy/info-flow-hub.service ~/.config/systemd/user/
systemctl --user daemon-reload
systemctl --user enable --now info-flow-hub
```
