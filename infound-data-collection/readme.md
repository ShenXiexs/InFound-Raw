## INFound Data Collection Services

Internal data collection services for enriching creator and product data in INFound. The repo includes reusable RabbitMQ consumer and Playwright scraping infrastructure (`common/`), plus two sample crawler implementations:

- `apps/portal_tiktok_sample_crawler`: API-based version (Partner API for sample list/content)
- `apps/portal_tiktok_sample_crawler_html`: HTML scraping version (Playwright, template/fallback)

> Quick overview
>
> 1. Config is composed from `configs/base.yaml` and `apps/<service>/configs/*.yaml`. The `SERVICE_NAME` env var decides which service is loaded.
> 2. `main.py` starts the specified consumer from CLI args and connects to RabbitMQ via `common.mq`.
> 3. Consumers read JSON tasks from RabbitMQ and pass them to the service layer (Playwright crawler in the example).

---

### Tech Stack

- Python 3.13 with Poetry
- Async stack: `asyncio`, `aio-pika` (RabbitMQ), `Playwright`
- Data access: SQLAlchemy 2 + AsyncMy (future reuse of `common.models`)
- Observability: `structlog`, concurrent-safe log rotation

---

## Repository Structure

```
infound-data-collection/
|-- apps/
|   |-- portal_tiktok_sample_crawler/           # API-based version
|   |   |-- crawler_consumer.py                 # RabbitMQ consumer entry
|   |   `-- configs/{base,dev}.yaml             # Service configs
|   |-- portal_tiktok_sample_crawler_html/      # Playwright HTML version
|   |   |-- crawler_consumer.py                 # RabbitMQ consumer entry
|   |   |-- services/crawler_runner_service.py  # Playwright runner logic
|   |   `-- configs/{base,dev}.yaml             # Service configs
|   `-- sample_chatbot/                         # Chatbot consumer (forwarder only)
|       |-- crawler_consumer.py                 # Consumer entry (dispatcher only)
|       |-- services/                           # Poll/dispatch logic skeleton
|       `-- configs/{base,dev}.yaml             # Service configs
|-- common/
|   |-- core/                                   # Config / logging / DB utilities
|   |-- mq/                                     # RabbitMQ connection and consumer base
|   `-- models/all.py                           # SQLAlchemy model collection
|-- configs/base.yaml                           # Global defaults
|-- main.py                                     # CLI entry
|-- rabbitmq_connect_test.py                    # RabbitMQ connectivity test
|-- pyproject.toml / poetry.lock
`-- readme.md
```

---

## Configuration Model

1. Environment variables
   - `SERVICE_NAME` (required): chooses `apps/<SERVICE_NAME>/configs`.
   - `ENV` (default `dev`): uses `apps/<SERVICE_NAME>/configs/<ENV>.yaml`.
   - Nested override is supported, for example `export RABBITMQ__PASSWORD=xxx`, `LOG_LEVEL=DEBUG`.
2. Config files
   - `configs/base.yaml`: shared defaults (system name, RabbitMQ creds, log dir, etc).
   - `apps/<service>/configs/base.yaml`: service-specific config (exchange, queue, auth token, etc).
   - `apps/<service>/configs/<env>.yaml`: environment overrides (example: `dev.yaml`).
3. Merge order
   - `common.core.config.Settings` flattens YAML and merges in order:
     global -> service base -> service env -> environment variables.
   - If `SERVICE_NAME` is not set, `settings` raises `ValueError` at import time.

---

## Local Run Guide

### 1. Prerequisites

- Python 3.13
- Poetry
- RabbitMQ access (scripts connect to a real server)
- Playwright browser deps (first run requires `playwright install`, Linux may need system deps)

### 2. Install dependencies

```bash
cd /Users/samxie/Research/Infound_Influencer/InFound_Back/infound-data-collection
poetry env use python3.13          # Set interpreter
poetry lock                        # Sync lock with pyproject
poetry install --no-root           # Install deps without packaging
poetry run playwright install      # Download browsers
# Optional: enter virtualenv
# poetry shell
```

### 3. Set environment variables

```bash
export SERVICE_NAME=portal_tiktok_sample_crawler_html
export ENV=dev        # Switch to stg/pro if present
export PLAYWRIGHT_HEADLESS=false     # Set false to see the browser locally
```

### 4. Start the consumer

```bash
poetry run python main.py --consumer portal_tiktok_sample_crawler_html --env "$ENV"
```

Optional flags:

- `--env`: override `ENV` temporarily (for example `--env stg`)
- `--all`: reserved for starting all consumers in `settings.CONSUMERS` (currently one)

Use `Ctrl+C` to exit. `main.py` traps SIGINT/SIGTERM and calls `consumer.stop()`.

### 5. Run in background (nohup example)

```bash
mkdir -p logs
nohup poetry run python main.py --consumer portal_tiktok_sample_crawler_html --env "$ENV" \
  > logs/portal_tiktok_sample_crawler_html.out 2>&1 &
tail -f logs/portal_tiktok_sample_crawler_html.out   # Follow output
```

To stop, find the PID and run `kill <pid>`.

---

## RabbitMQ Integration

- `common.mq.connection.RabbitMQConnection`
  - Declares a direct exchange plus a dedicated DLX (`<exchange>.dlx`) and DLQ (`<queue>.dead`).
  - Configurable QoS, reconnect interval, and max retries.
  - Structured logs for connect/close state.
- `common.mq.consumer_base.ConsumerBase`
  - Unified consume loop with auto reconnect.
  - Parses JSON body and attaches context logs, with error handling:
    - `ValueError`: `reject(requeue=False)` (bad format, no retry)
    - `MessageProcessingError`: `reject(requeue=True)` (business retry)
    - Other errors: `reject(requeue=False)` (avoid endless loops)
  - Uses `async with message.process()` for manual ACK/NACK.

Example consumer `apps/portal_tiktok_sample_crawler_html/crawler_consumer.py` extends the base, builds RabbitMQ connection from config, and delegates to `CrawlerRunnerService`.

---

## Collector -> Inner API Ingestion Pipeline

`portal_tiktok_sample_crawler_html` no longer writes to DB directly. It posts each batch of normalized rows to the backend inner API (`POST /samples/ingest`) via `SampleIngestionClient`. The inner API aggregates content summary, de-duplicates content, and writes to the DB. Details:

1. `apps/portal_tiktok_sample_crawler_html/services/sample_ingestion_client.py` wraps `httpx.AsyncClient` calls, auth, and error handling. When `RABBITMQ.AT_MOST_ONCE=true`, tasks do not retry; failures are logged and best-effort pushed to DLQ.
2. `CrawlerRunnerService._persist_results` bundles `CrawlOptions` (`dataclasses.asdict`) and normalized `rows`, and includes `source` (default `settings.CONSUMER`) and `operatorId`.
3. `apps/portal_tiktok_sample_crawler_html/configs/base.yaml` adds `INNER_API` config, overridable by env vars:
   ```yaml
   INNER_API:
     BASE_URL: "<INNER_API_BASE_URL>"
     SAMPLE_PATH: "/samples/ingest"
     TIMEOUT: 30
   INNER_API_AUTH:
     REQUIRED_HEADER: "X-INFound-Inner-Service-Token"
     VALID_TOKENS: ["<INNER_API_TOKEN>"]
   ```
   In production, set `INNER_API__BASE_URL` and `INNER_API_AUTH__TOKEN` only.
4. The collector can still export Excel/CSV. As long as inner API is reachable, the task can complete even if DB is not directly accessible, reducing Playwright permissions.

### Request/response contract

- URL: `${INNER_API.BASE_URL}${INNER_API.SAMPLE_PATH}`
- Headers:
  - `Content-Type: application/json`
  - `${INNER_API_AUTH.REQUIRED_HEADER}: <token>`
- Body:
  ```json
  {
    "source": "portal_tiktok_sample_crawler_html",
    "operatorId": "00000000-0000-0000-0000-000000000000",
    "options": {
      "campaignId": "7563877506852587284",
      "tabs": ["completed"],
      "region": "MX",
      "scanAllPages": true,
      "expandViewContent": true,
      "viewLogistics": true,
      "exportExcel": false
    },
    "rows": [{ "...": "Playwright normalized fields" }]
  }
  ```
- Success response: `{"code": 200, "msg": "success", "data": {"inserted": 40, "products": 9}}`
- Error response: inner API returns non-200 code or HTTP 4xx/5xx; client logs and raises `MessageProcessingError`.

---

## Sample Series Notes

Currently the queue supports only the "Sample" series. Each message must include `function: "sample"` (CLI defaults include it). If new functions are added, `function` can be used for routing.

### Tab mapping

| MQ `tab` value | Page title        | URL parameter           |
|---------------|-------------------|-------------------------|
| `review`      | To review         | `tab=to_review`         |
| `ready`       | Ready to ship     | `tab=ready_to_ship`     |
| `shipped`     | Shipped           | `tab=shipped`           |
| `pending`     | Content pending   | `tab=content_pending`   |
| `completed`   | Completed         | `tab=completed`         |
| `canceled`    | Canceled          | `tab=cancel`            |
| `all`         | Iterate all tabs  | *switch in order*       |

`tab=all` switches in order: To review -> Ready to ship -> Shipped -> Content pending -> Completed -> Canceled.

---

## Playwright Crawler Service

`apps/portal_tiktok_sample_crawler_html/services/crawler_runner_service.py` fully mirrors the legacy `sample_all.py` + `sample_process.py` behavior. Key features:

- Account and region management: select accounts via config or MQ messages, disable accounts, switch regions, includes Gmail OTP login flow.
- Auto monitoring and scraping: stay on home page after login, listen to RabbitMQ messages and poll by tab (All/To review/Ready...). Each message handles one campaign ID.
- Precise filtering: with `campaignId`, fill search box and crawl pages; `scanAllPages=true` iterates all pages in the tab.
- Action parsing: parses View content drawer (video/live, retries), View logistics snapshot (basic info + timeline + raw text), and Approve button state.
- Normalization and persistence: formats fields per `sample_process.py` rules, aggregates content_summary (dedupe + logistics insert), and updates `samples`, `sample_crawl_logs`, `sample_contents`, `sample_content_crawl_logs`.
- Optional export: when `exportExcel=true`, exports normalized rows to `data/manage_sample/samples_<region>_<campaign>_<tabs>_<ts>.{xlsx,csv}` for review.

### MQ message fields (lower camelCase recommended)

| Field                 | Type           | Description                                                  |
|-----------------------|----------------|--------------------------------------------------------------|
| `function`            | `str`          | Task type, currently only `sample`                           |
| `campaignId`          | `str`          | Optional, campaign ID                                        |
| `accountName`         | `str`          | Optional, override account                                   |
| `region`              | `str`          | Optional, default `settings.SAMPLE_DEFAULT_REGION`           |
| `tab` / `tabs`        | `str / list`   | Tabs to scan (`all`/`review`/`ready`/...)                    |
| `expandViewContent`   | `bool`         | Expand View content drawer and parse video/live              |
| `viewLogistics`       | `bool`         | Click View logistics and save snapshot                       |
| `scanAllPages`        | `bool`         | If true, paginate all pages; with `campaignId` default is first match only
| `maxPages`            | `int`          | Max pages to prevent infinite loops                          |
| `exportExcel`         | `bool`         | Export Excel/CSV before DB write                             |

All fields can be set with defaults in `configs/*.yaml`.

### MQ message examples

- Most common (single campaign, Completed tab):

```json
{
  "function": "sample",
  "tab": "completed",
  "region": "MX",
  "campaignId": "7563877506852587284",
  "scanAllPages": true,
  "expandViewContent": true,
  "viewLogistics": true,
  "exportExcel": true
}
```

- Multiple campaign IDs in order (search, wait 5 to 8 seconds per ID):

```json
{
  "campaignIds": ["123", "456", "789"],
  "tab": "review",
  "region": "MX",
  "scanAllPages": true,
  "expandViewContent": true,
  "viewLogistics": true,
  "exportExcel": false
}
```

Behavior: for each campaign, switch to tab, type search, press enter or click search, wait about 5 seconds, crawl, clear search, move to next ID.

- Full traversal for current tabs (no campaign filter):

```json
{
  "tab": "all",
  "region": "MX",
  "scanAllPages": true,
  "expandViewContent": true,
  "viewLogistics": true,
  "exportExcel": false
}
```

`tab=all` iterates To review / Ready to ship / Shipped / Content pending / Completed / Canceled. If `campaignId` is provided, search filtering is applied; otherwise it crawls full lists.

- Specific campaign ID with full pagination:

```json
{
  "campaignId": "123456789",
  "tab": "review",
  "region": "MX",
  "scanAllPages": true,
  "expandViewContent": true,
  "viewLogistics": true,
  "exportExcel": false
}
```

Send JSON to exchange `crawler.direct` (split by tab routing). The single process `portal_tiktok_sample_crawler` consumes:

- Completed queue: routing key `crawler.tiktok.sample.completed.key` -> queue `crawler.tiktok.sample.completed.queue`
- Other queue: routing key `crawler.tiktok.sample.other.key` -> queue `crawler.tiktok.sample.other.queue`

### Crawl and persistence flow

1. Login and home monitoring: start Playwright, complete Gmail OTP login, record tab count baseline.
2. Task execution: for each tab -> clear or input campaign ID -> paginate and call `_crawl_current_page`. Each row records base fields plus button states and creator details.
3. Action expansion:
   - View content: parse video/live metrics with retries and drawer close handling.
   - View logistics: parse description list, table, timeline, raw text; stored in `content_summary` (`type="logistics"`) and exported as JSON.
4. Normalization: numbers, percentages, and time fields are converted to int or Decimal; `content_summary` is deduped by `platform_product_id` and ensures unique promotion/logistics entries.
5. DB write and export: upsert into four sample tables and export Excel/CSV as configured.

Playwright dependencies must be installed with `poetry run playwright install`. It is recommended to call `initialize()` once at consumer startup to reuse the browser instance.

### Feature list (aligned with legacy `sample_all.py` / `sample_process.py`)

- Account strategy: multi-account config, disabled slots, region match priority; MQ can specify `accountName`/`region`, fallback to default.
- Login and OTP: Gmail App Password based OTP retrieval; retries up to 3 times.
- Home monitoring: record tab counts and compare deltas before tasks.
- Message protocol: supports tab arrays, region/account overrides, content drawer toggle, logistics toggle, full pagination, max pages, export flags.
- Search and pagination: with `campaignId` and no full scan, only crawl matched rows; full scan clears search and paginates with retries.
- Row parsing: product/campaign ID, SKU, inventory, available samples, status, remaining time, post_rate, is_showcase, creator info.
- Action parsing: detect View content / View logistics / Approve, record disabled state; optional logistics drawer parsing.
- View content drawer: retries, parse metrics by Video/Live tab, handle special layouts and empty fallback.
- View logistics drawer: parse description list, tables, timeline, raw text; store as `type="logistics"` in content_summary.
- Field normalization: same rules as `sample_process.py` including compact numbers (k/m), percentages, time remaining, boolean normalization; avoid scientific notation.
- content_summary dedupe: per product JSON de-dup for promotion/logistics entries; if empty, write an empty summary to keep JSON valid.
- DB write: upsert `samples`, `sample_crawl_logs`, `sample_contents`, `sample_content_crawl_logs`. Timestamps are UTC; operator uses `settings.SAMPLE_DEFAULT_OPERATOR_ID`.
- Export: if `exportExcel=true`, export normalized rows to `data/manage_sample/samples_<region>_<campaign>_<tabs>_<ts>.xlsx/csv`, JSON-encode list/JSON fields for review.

## Sample Chatbot (MX region)

- Startup: set `SERVICE_NAME=sample_chatbot`, `ENV=<env>`, then run `poetry run python main.py --consumer sample_chatbot`.
- Responsibilities:
  - Inner API: writes `sample_chatbot_schedules` after ingestion (status change and reminder rules), and publishes batches to MQ via a background task.
  - `sample_chatbot`: only consumes MQ and sends chat messages via Playwright (no DB polling, no template management).
- RabbitMQ (topic) conventions:
  - Exchange: `chatbot.topic`
  - Queue: `chatbot.sample.queue.topic` (DLQ: `chatbot.sample.queue.topic.dead`, DLX: `chatbot.topic.dlx`)
  - Publish routing key: `chatbot.sample.batch` (queue binding: `chatbot.sample.*`)
- Message format (lower camelCase; `messages` required, can send array or wrap with `tasks`):
  - Task array (recommended):
    ```json
    [
      {
        "region": "MX",
        "platformCreatorId": "7341888112345678901",
        "messages": [
          { "type": "text", "content": "Hi *" },
          { "type": "link", "content": "https://**" }
        ]
      }
    ]
    ```
  - Batch wrapper (compatible):
    ```json
    {
      "taskId": "BATCH-UUID",
      "tasks": [
        {
          "region": "MX",
          "platformCreatorId": "7341888112345678901",
          "messages": [
            { "type": "text", "content": "Hi *" },
            { "type": "link", "content": "https://**" }
          ]
        }
      ]
    }
    ```
  - Optional fields: `accountName`, `from`/`operatorId`, `sampleId`, `platformProductId`, `platformProductName`, `platformCampaignName`, `platformCreatorUsername`, `creatorWhatsapp`.
- Message generation: Inner API or ops tooling generates content and sends; `sample_chatbot` only forwards `messages`.
- Failures and replay:
  - Failed task is moved to DLQ `chatbot.sample.queue.topic.dead` (does not drop the whole batch).
  - Use `poetry run python tools/requeue_chatbot_dlq.py --consumer sample_chatbot --env <env>` to republish DLQ messages.

## Creator Outreach

### Run pipeline (crawler -> Inner API -> MQ/send)

1. `portal_tiktok_creator_crawler` logs in via Playwright, filters, scrolls, and scrapes creator details and contacts.
2. Each creator row is posted to Inner API `/creators/ingest` (tables `creators` + `creator_crawl_logs`).
3. Task progress and status are synced to Inner API `/outreach_tasks/ingest`.
4. If send conditions are met, it sends message tasks to Inner API `/chatbot/messages`, which forwards to RabbitMQ for `sample_chatbot` to deliver.

### Inner API calls

- Create or update outreach task: `POST /outreach_tasks/ingest`
  - Body (lower camelCase; `task` can include extra fields):
    ```json
    {
      "source": "portal_tiktok_creator_crawler",
      "operatorId": "ACCOUNT_UUID",
      "task": {
        "taskId": "UUID",
        "platform": "tiktok",
        "taskName": "Campaign Outreach",
        "campaignId": "123",
        "campaignName": "Campaign",
        "productId": "456",
        "productName": "Product",
        "region": "MX",
        "brand": "Brand",
        "onlyFirst": 0,
        "taskType": "Connect",
        "status": "running",
        "message": "optional",
        "accountEmail": "account@example.com",
        "searchKeywords": "kw1,kw2",
        "productCategory": ["Beauty & Personal Care"],
        "fansAgeRange": ["18-24"],
        "fansGender": "Female 60%",
        "contentType": ["Video"],
        "gmv": ["1k-10k"],
        "sales": ["10-100"],
        "minFans": 5000,
        "avgViews": 5000,
        "minEngagementRate": 3,
        "emailFirstBody": "text",
        "emailLaterBody": "text",
        "targetNewCreators": 50,
        "maxCreators": 500,
        "runAtTime": "2025-01-01 10:00:00",
        "runEndTime": "2025-01-01 12:00:00",
        "runTime": "00h10min00s",
        "newCreators": 12,
        "startedAt": "2025-01-01 10:00:00",
        "finishedAt": "2025-01-01 11:00:00",
        "createdAt": "2025-01-01 09:00:00"
      }
    }
    ```
  - `operatorId`: account/operator UUID used for audit fields.

- Creator ingestion: `POST /creators/ingest`
  - Body: `source` / `operatorId` / `options` / `rows`; `rows` includes
    `creator_id`, `creator_name`, `categories`, `followers`, `gmv`, `contact`,
    `connect/reply/send` etc.

- Message tasks: `POST /chatbot/messages`
  - Payload matches the sample chatbot format; inner API forwards to RabbitMQ.

### RabbitMQ conventions

- Exchange and queue shared with `sample_chatbot`:
  - Exchange: `chatbot.topic`
  - Queue: `chatbot.sample.queue.topic` (DLQ: `chatbot.sample.queue.topic.dead`, DLX: `chatbot.topic.dlx`)
  - Routing key: `chatbot.sample.batch` (queue binding: `chatbot.sample.*`)

### Field normalization and persistence mapping (aligned with `sample_process.py`)

- IDs: `platform_product_id` required; `platform_campaign_id` normalized (trim, remove leading zeros for numeric). Empty rows are dropped.
- Numbers: `available_sample_count`, `stock`, `promotion_view/like/comment/order` -> int; `post_rate`, `promotion_order_total_amount` -> Decimal.
- Time/strings: `request_time_remaining` normalized to "X days/hours"; `extracted_time` stored as UTC string.
- Booleans: `is_showcase`, `is_uncooperative`, `is_unapprovable` default to 0/False.
- Creator info: `platform_creator_display_name`, `platform_creator_username`, `platform_creator_id`, `creator_url` are persisted; username strips leading @.
- content_summary: aggregate by `platform_product_id`, include Video/Live promotions and logistics events, and avoid duplicates; if empty, write one empty summary.
- Log tables: `SampleCrawlLogs` stores full rows by day; `SampleContentCrawlLogs` stores per content item (Video/Live).
- Export column order: keep legacy Excel column order and include JSON for `actions`, `action_details`, `logistics_snapshot`.

### Operational tips

1. Config prep: update `apps/portal_tiktok_sample_crawler_html/configs/*.yaml` for account, region, default tab, and switches (`SAMPLE_EXPAND_VIEW_CONTENT`, `SAMPLE_VIEW_LOGISTICS_ENABLED`, `SAMPLE_ENABLE_EXCEL_EXPORT`).
2. Run: set `SERVICE_NAME=portal_tiktok_sample_crawler_html`, start consumer; publish MQ message with `{"campaignId": "...", "viewLogistics": true, "exportExcel": true}` to validate.
3. Verify: watch logs for tab count diff and login success; check `data/manage_sample/` exports and DB tables `samples` / `sample_contents`.
4. Troubleshoot: login/drawer timeout retries are built in; if UI changes, update `SAMPLE_SEARCH_INPUT_SELECTOR` or selector snippets and re-run.

### Sample crawler account config

- Account config file: `configs/accounts.json` (set by `SAMPLE_ACCOUNT_CONFIG_PATH`, already created). MQ messages can use `accountName` and `region` to force selection; otherwise selection is by region match -> enabled-first. Disabled accounts (`enabled=false`) are skipped.
- Current built-in accounts:
  - `MX1` (region MX): `mx1@example.com` / Gmail App Password `<GMAIL_APP_PASSWORD>`
  - `MX2` (region MX): `mx2@example.com` / Gmail App Password `<GMAIL_APP_PASSWORD>`
  - `MX3` (region MX): `mx3@example.com` / Gmail App Password `<GMAIL_APP_PASSWORD>`
  - `MX4` (region MX, disabled, needs launcher code): `mx4@example.com` (disabled, password empty)
  - `FR1` (region FR): `fr1@example.com` / Gmail App Password `<GMAIL_APP_PASSWORD>`
- Single-account fallback: if `accounts.json` is missing, fallback to `SAMPLE_LOGIN_EMAIL` / `SAMPLE_GMAIL_USERNAME` / ... in `apps/portal_tiktok_sample_crawler_html/configs/base.yaml`.
- Suggestion: reorder `accounts.json` to change priority, or set `enabled=false`; pass `region` in MQ messages for cross-region tasks.

---

## Data Access Tools

- `common.core.database`
  - Creates async SQLAlchemy engine from `settings.SQLALCHEMY_DATABASE_URL`.
  - Exposes `get_db()` context manager for session injection.
- `common.models/all.py`
  - `sqlacodegen` generated INFound models for campaigns, creators, samples, etc.
  - Can be imported as needed (for example `from common.models.all import Creators`).

Some example consumers do not write to DB yet, but the modules are ready.

---

## Logs and Observability

- `common.core.logger`
  - Based on `structlog`, outputs console logs (local time, readable) and file logs (JSON, concurrent-safe rotation).
  - Log files live under `logs/<APP_NAME>.log`; adjust via `LOG_DIR`, `LOG_FILE_MAX_SIZE`, `LOG_FILE_BACKUP_COUNT`.
  - Automatically merges context fields (consumer name, request ID, etc).
- `common.core.exceptions`
  - Central exceptions like `RabbitMQConnectionError`, `MessageProcessingError`, `PlaywrightError` for consistent handling.

---

## Tools and Troubleshooting

- `rabbitmq_connect_test.py`

  ```bash
  poetry run python rabbitmq_connect_test.py
  ```

  Uses `aio-pika.connect_robust` to verify connectivity, helpful for firewall or credential issues. Update `configs/base.yaml` or use env vars for alternate creds.

---

## Steps to Add a New Consumer

1. Create the directory structure:
   ```
   apps/<new_consumer>/
     |-- crawler_consumer.py
     |-- services/...
     `-- configs/{base,dev,stg,pro}.yaml
   ```
2. Add the service name to `CONSUMERS` in `configs/base.yaml`.
3. Set `SERVICE_NAME=<new_consumer>` before running.
4. Validate the message in `process_message_body`, call business logic, and raise `MessageProcessingError` for retryable cases.

This structure maximizes reuse of RabbitMQ, logging, and configuration logic while keeping business logic focused.

---

## Development Workflow

- Format: `poetry run black .`
- Lint: `poetry run flake8`
- Add dependencies: `poetry add <package>`; lock file: `poetry lock --no-update`
- Tests: no built-in test folder yet, add `tests/` if needed

Keep config decoupled from environment, and update README when adding new consumers. Prefer exceptions from `common.core.exceptions` for consistent handling.

---

## FAQ

- Why does importing `common.core.config` fail immediately? Because config is instantiated at import time and shared across modules. Missing `SERVICE_NAME` throws before startup.
- How do I configure RabbitMQ per environment? Add `stg.yaml`/`pro.yaml` under `apps/<service>/configs/` and override `RABBITMQ: {HOST: "...", ROUTING_KEY: "...", ...}`. Env vars can still override sensitive fields.
- Where are production logs written?
  Default is `logs/` under the repo. In containers, mount the directory or route logs to your log system.
