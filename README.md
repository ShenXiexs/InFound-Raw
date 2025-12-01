# TikTok Partner Crawler Backend

A FastAPI + Playwright backend that orchestrates account pooling, task scheduling, product management, and outreach tooling for TikTok Shop partner workflows. This document is fully in English and intentionally omits any production-only hostnames or tokens so the repository can be shared publicly.

## Overview
- **Stack**: FastAPI, SQLAlchemy, Playwright, Pandas, and Pydantic.
- **Capabilities**: task scheduling, outreach automation, chat/card tooling, sample management, and product ingestion.
- **Data stores**: SQLite by default (`data/infound_dev.db`) with optional overrides via `DB_URL`.
- **Processes**: background crawlers driven by task definitions plus auxiliary scripts for card sending, chat history export, and sample scraping.

## Project Structure
```
api/                 # FastAPI routers
config/              # Sample JSON configs (accounts, users)
core/                # Settings, security, and shared config
crawler/             # Playwright crawlers and task workers
chat_history/        # Chat related utilities
product_card/        # Card generation & sending scripts
services/            # Business logic for API endpoints
schemas/             # Pydantic models
models/              # Playwright flows and helpers
utils/               # Shared helpers (responses, exceptions, etc.)
data/                # Example data, tasks, and exports
logs/                # Local log output (ignored in production)
```

## Prerequisites
- Python 3.10.18
- Node dependencies handled by Playwright (`playwright install chromium`)
- Optional: `sqlite3` CLI for quick DB inspections

## Local Environment Setup
```bash
python3 -m venv .venv
source .venv/bin/activate
pip install --upgrade pip
pip install -r requirements_api.txt
playwright install chromium
cp .env.example .env   # optional overrides (DB_URL, SECRET_KEY, etc.)
```

Key configuration files:
- `config/accounts.json`: account pool definition (placeholders, update with your credentials).
- `config/users.json`: API user definitions (hashed passwords only).
- `.env`: overrides for values in `core/config.py` (e.g., DB path, host, port, log level).

## Running the API
```bash
python main.py                            # development with built-in uvicorn
python main.py --host 0.0.0.0 --port 8000 # explicit host/port
nohup python main.py > logs/api/server.log 2>&1 &
```
Swagger UI lives at `http://127.0.0.1:8000/docs`. Health endpoint is `http://127.0.0.1:8000/health`.

To stop background processes, locate the PID via `pgrep -f "python main.py"` (or uvicorn) and kill it, or use the helper script described below.

## Helper Script
`scripts/server_manage.sh` automates dependency installation and uvicorn process management. Usage:
```
./scripts/server_manage.sh setup  # create venv + install deps (once)
./scripts/server_manage.sh start  # start uvicorn in the background
./scripts/server_manage.sh stop   # stop the background process
./scripts/server_manage.sh status # show current process status
```

## Authentication & Credentials
- No production tokens are stored in this repository.
- Default login details in code were replaced with environment-driven placeholders.
- Set the following env vars (or supply `account_info` objects) before running crawlers:
  - `DEFAULT_TTSHOP_EMAIL`
  - `DEFAULT_TTSHOP_PASSWORD`
  - `DEFAULT_GMAIL_USERNAME`
  - `DEFAULT_GMAIL_APP_PASSWORD`
- `config/accounts.json` ships with synthetic entries—replace them with real, secret-managed credentials (env vars, HashiCorp Vault, etc.) prior to deployment.

## Submitting Tasks Locally
1. Authenticate:
   ```bash
   TOKEN=$(curl -s -X POST http://127.0.0.1:8000/api/v1/auth/login \
     -H "Content-Type: application/x-www-form-urlencoded" \
     -d "username=admin&password=<your-password>" | jq -r '.data.access_token')
   ```
2. Submit a task:
   ```bash
   curl -X POST http://127.0.0.1:8000/api/v1/crawler/tasks \
     -H "Authorization: Bearer $TOKEN" \
     -H "Content-Type: application/json" \
     -d @task_json/jeep-monster_task.json
   ```
3. Inspect status/logs via `/api/v1/crawler/tasks/{task_id}` and `/api/v1/crawler/tasks/{task_id}/log`.

All bearer tokens above are placeholders; generate your own via the login endpoint.

## Database Utilities
- Default DB file: `data/infound_dev.db`. Override by setting `DB_URL` in `.env`.
- Initialize tables: `python -m database.create_tables`.
- Ingest creators: `python -m database.ingest_creator_excel --file data/creator.xlsx --region MX`.
- Product ingestion via Excel: `python -m database.ingest_product_excel --file data/product_data/product_list.xlsx`.
- View stats: `python -m database.view_database --tables` or pass `--sql` for ad-hoc queries.

## Product Upload API Flow
```bash
curl -X POST http://127.0.0.1:8000/api/v1/product/upload-excel \
  -H "Authorization: Bearer $TOKEN" \
  -F "file=@data/product_data/product_list.xlsx" \
  -F "note=demo import" \
  -F "use_dify=false"
```
Poll `/api/v1/product/upload-progress/{batch_id}` or `/api/v1/product/upload-progress/summary` to monitor progress. Sample responses include batch counts, total rows, and estimated completion time.

## Product & Card APIs (Examples)
- `GET /api/v1/product/list?pageNum=1&pageSize=20`
- `GET /api/v1/product/items/{id}`
- `PUT /api/v1/product/items/{id}`
- `POST /api/v1/product/batch`
- `POST /api/v1/card/tasks` for uploading creator/product Excel sheets and optionally triggering automated sending (headless Playwright).

Card-related endpoints accept `creator_file`, `product_file`, `headless`, `verify_delivery`, and `generate_only` flags. JSON output lands under `data/card/tasks/<task_id>/`.

## API Reference & Calls

### Authentication
```bash
curl -X POST http://127.0.0.1:8000/api/v1/auth/login \
  -H "Content-Type: application/x-www-form-urlencoded" \
  -d "username=admin&password=<password>"
```
Response:
```json
{
  "success": true,
  "data": {
    "access_token": "<JWT>",
    "token_type": "bearer",
    "expires_in": 86400
  }
}
```

### Task Management
- `POST /api/v1/crawler/tasks`
- `GET /api/v1/crawler/tasks?pageNum=1&pageSize=20`
- `GET /api/v1/crawler/tasks/{task_id}`
- `PUT /api/v1/crawler/tasks/{task_id}`
- `DELETE /api/v1/crawler/tasks/{task_id}`
- `POST /api/v1/crawler/tasks/{task_id}/run-now`
- `GET /api/v1/crawler/tasks/{task_id}/log`

Creating a task:
```bash
curl -X POST http://127.0.0.1:8000/api/v1/crawler/tasks \
  -H "Authorization: Bearer $TOKEN" \
  -H "Content-Type: application/json" \
  -d @task_json/jeep-monster_task.json
```

### Accounts & Samples
- `GET /api/v1/accounts` – list configured account pool entries.
- `POST /api/v1/accounts` – add/update accounts (use environment variables or secrets manager; payload excludes plaintext passwords when sharing).
- `GET /api/v1/sample/tasks` – inspect sample crawling jobs.
- `POST /api/v1/sample/tasks` – trigger sample crawlers with region/tab payloads.

### Product APIs
- `GET /api/v1/product/list?pageNum=1&pageSize=20`
- `GET /api/v1/product/items/{id}`
- `GET /api/v1/product/items/by-product-id/{product_id}`
- `POST /api/v1/product/upload-excel`
- `POST /api/v1/product/sync-from-excel`
- `POST /api/v1/product/batch`
- `DELETE /api/v1/product/items/{id}`

Example call:
```bash
curl -G http://127.0.0.1:8000/api/v1/product/list \
  -H "Authorization: Bearer $TOKEN" \
  --data-urlencode "pageNum=1" \
  --data-urlencode "pageSize=20" \
  --data-urlencode "region=MX"
```

### Card APIs
- `POST /api/v1/card/tasks` – upload creator/product Excel and optionally dispatch chats.
- `GET /api/v1/card/tasks` – list historical card runs.
- `GET /api/v1/card/tasks/{task_id}` – inspect details, including generated JSON.
- `POST /api/v1/card/tasks/{task_id}/cancel`

Example call (generate-only):
```bash
curl -X POST http://127.0.0.1:8000/api/v1/card/tasks \
  -H "Authorization: Bearer $TOKEN" \
  -F "creator_file=@data/card/creator_info.xlsx" \
  -F "product_file=@data/card/product_info.xlsx" \
  -F "generate_only=true"
```

### Chat APIs
- `GET /api/v1/chat/history?creator_id=<id>` – fetch saved chat logs (if chat crawlers persisted data).
- `POST /api/v1/chat/tasks` – schedule background chat crawlers.

All API routes follow the same pattern: login for a JWT, include the bearer token in `Authorization`, and use `application/json` or multipart forms as documented. Swagger/OpenAPI docs remain accessible at `/docs` for full schema details.

## Deployment Checklist
1. Provision a server (Linux preferred) and secure SSH access (use your own hostname/IP, not included here).
2. Install system dependencies (`python3.10`, `chromium`, fonts) and copy the repository.
3. Set environment variables or `.env.production` with strong values (`SECRET_KEY`, `DB_URL`, `ALLOWED_ORIGINS`, credentials, etc.).
4. Run `./scripts/server_manage.sh setup && ./scripts/server_manage.sh start` or create a `systemd` unit pointing to your virtual env.
5. Expose the API via a reverse proxy (Nginx/HTTPS) using your own domain.

Example `systemd` snippet (customize paths and user):
```ini
[Unit]
Description=TikTok Partner API
After=network.target

[Service]
WorkingDirectory=/opt/apps/tiktok_partner_back
Environment="UVICORN_NO_UVLOOP=1"
Environment="PATH=/opt/python/envs/infound/bin:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"
ExecStart=/opt/python/envs/infound/bin/uvicorn main:app --host 0.0.0.0 --port 8000 --loop asyncio
Restart=always
RestartSec=5
User=app

[Install]
WantedBy=multi-user.target
```

## Security & Privacy Notes
- Replace every placeholder credential before deployment.
- Store secrets outside of version control (prefer env vars or a vault).
- Rotate API tokens regularly; JWT expiration defaults to 24 hours and can be updated in `core/config.py`.
- Logs may contain sensitive runtime data—ensure `logs/` is not committed when publishing.

## Common Issues
- **Playwright startup failures**: run `playwright install chromium` and install OS-level dependencies.
- **Gmail verification not arriving**: verify app passwords and IMAP access; ensure env vars are set correctly.
- **Tasks stuck in pending**: inspect `logs/api/server.log` and the account pool to ensure the crawler has valid credentials.
- **Excel conflicts**: file writes are guarded by `filelock`, but large exports can still clash—copy files before editing externally.

## Contributing
1. Create a new virtual environment and install dependencies.
2. Format code with `black`/`ruff` (optional) and keep comments/docstrings in English.
3. Before sharing or pushing, ensure no secrets or hostnames leak into README/issues/logs.
