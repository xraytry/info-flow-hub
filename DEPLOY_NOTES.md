COMMIT:
Use the latest pushed HEAD of `main`.

BRANCH:
main

APP_PATH:
/home/lhb/info-flow-hub

DB_PATH:
/home/lhb/info-flow-hub/info_flow_hub.db

PORT:
8030

CDP_URL:
http://127.0.0.1:9222

DEPENDENCY_CHANGED:
Initial repository. Python and npm dependencies must be installed.

DB_MIGRATION_REQUIRED:
Initial repository creates SQLite schema on startup. No migration from another app is required.

INSTALL_COMMAND:
```bash
cd /home/lhb/info-flow-hub
python3 -m venv .venv
.venv/bin/python -m pip install -r backend/requirements.txt
npm install
npm run build
INFO_FLOW_DB=/home/lhb/info-flow-hub/info_flow_hub.db .venv/bin/python backend/scripts/init_sources.py
```

START_COMMAND:
```bash
cd /home/lhb/info-flow-hub
INFO_FLOW_DB=/home/lhb/info-flow-hub/info_flow_hub.db PORT=8030 CDP_URL=http://127.0.0.1:9222 .venv/bin/python backend/run.py
```

VERIFY_COMMANDS:
```bash
cd /home/lhb/info-flow-hub
.venv/bin/python -m compileall backend
.venv/bin/python -m unittest discover -s backend/tests -v
npm run build
curl -sS http://127.0.0.1:8030/api/health
```

ROLLBACK_NOTE:
This is the first release. Roll back by stopping `info-flow-hub.service` and checking out the previous known good commit after one exists.
