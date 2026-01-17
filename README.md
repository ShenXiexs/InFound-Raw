# INFound Influencer Platform (Backend + Data Collection)

This workspace pairs FastAPI backend services with Playwright- and RabbitMQ-powered data collectors to showcase the sample ingestion, creator outreach, and chatbot automation flows that support the INFound influencer pipeline. The materials are curated for an UCSD MS committee presentation, so every sensitive string has been sanitized.

## Architecture snapshot

- `infound-backend-services` houses the internal ingestion API, creator portals, request filters, scheduler, and MQ producers that run inside FastAPI processes.
- `infound-data-collection` implements RabbitMQ consumers, Playwright crawlers, and chatbot dispatchers that normalize TikTok partner data and hand it to the backend.
- Shared helpers in `common/` modules centralize multi-environment config, structured logging, SQLAlchemy/Redis sessions, RabbitMQ connections, and model definitions so business logic can stay focused.

## Backend services

- Internal ingestion APIs under `apps/portal_inner_open_api` rely on `SampleIngestionService`, `RequestFilterMiddleware`, and Pydantic models to validate rows, deduplicate `samples`/`sample_contents`, persist `*_crawl_logs`, and maintain `sample_chatbot_schedules`.
- `ChatbotSchedulePublisher` periodically polls due schedules, builds follow-up content via `chatbot_message_builder`, and publishes tasks to `chatbot.topic` through the shared `RabbitMQProducer`; `/chatbot/messages` accepts prebuilt payloads as well.
- Creator portals under `apps/portal_creator_open_api` provide login plus sample/chatbot endpoints, while the inner API exposes `/creators/ingest`, `/outreach_tasks/ingest`, and `/chatbot/messages` so crawlers can ingest creator metadata, sync outreach task state, and request message dispatch.
- Common infrastructure (`common/core/config.py`, `common/core/logger.py`, `common/core/database.py`, `common/services/redis_service.py`, etc.) keeps configuration, logging, database pooling, and Redis helpers consistent across services.

## Data collection services

- `common/mq` contains a resilient `RabbitMQConnection` and `ConsumerBase` that every consumer inherits; they auto-handle reconnection, error classification (`MessageProcessingError`, `ValueError`), and JSON parsing with contextual logs.
- `apps/portal_tiktok_sample_crawler_html` rebuilds the legacy `sample_all.py`/`sample_process.py` workflow with `CrawlerRunnerService`, Playwright browser pools, Gmail code handlers, account/region selection, tab navigation, view-content/logistics extraction, and data normalization/export routines that still align with `samples`, `sample_contents`, and `sample_chatbot_schedules` through `SampleIngestionClient`.
- `apps/portal_tiktok_campaign_crawler` logs into TikTok Shop Partner Center, crawls campaign/product tables, optionally exports Excel snapshots, and posts normalized payloads to `/campaigns/ingest` and `/products/ingest` via `CampaignIngestionClient`.
- `apps/portal_tiktok_creator_crawler` gathers creator metadata, contact info, and outreach-relevant stats, then posts them to the inner API endpoints for creator ingestion, outreach task syncing, and chatbot scheduling.
- `apps/sample_chatbot`, `apps/outreach_chatbot`, and `apps/unified_chatbot` consume the `chatbot.topic` exchange, respect DLQs, and use Playwright instances to send sample and outreach messages, while providing manual overrides for accounts/regions and retry limits.
- RabbitMQ tasks are routed through `crawler.direct`, `chatbot.topic`, and their DLQs; each consumer can also be run with `AT_MOST_ONCE` semantics or batched delivery and can export normalized rows to `data/manage_sample/` or `data/manage_campaign/` when `exportExcel` is enabled.

## Committee showcase: sample crawler, campaign crawler, creator crawler, and chatbots

- **Sample crawler story**: the Playwright-backed `portal_tiktok_sample_crawler_html` service drives `[region, tab, campaign]` exploration, extracts content/logistics/promotions, enforces the same normalization rules as `sample_process.py`, exports verification files, then hands every batch to `/samples/ingest` via `SampleIngestionClient`. This chain demonstrates the playbook for how TikTok sample requests become structured data.
- **Campaign crawler story**: `portal_tiktok_campaign_crawler` logs into Partner Center, scans campaigns or specific IDs, opens campaign detail tables, exports optional spreadsheets, and ships campaign/product rows to `/campaigns/ingest` and `/products/ingest` for catalog seeding and monitoring.
- **Creator crawler story**: `portal_tiktok_creator_crawler` logs into the partner creator portal, scrolls results, captures creator stats/contact info, and calls `/creators/ingest`/`/outreach_tasks/ingest` to sync records with the backend. It showcases how outreach datasets and creator contact pipelines are seeded before any chatbot outreach is scheduled.
- **Chatbot story**: `sample_chatbot`, `outreach_chatbot`, and `unified_chatbot` consume `chatbot.topic`, honor DLQs, and use Playwright to send the prepared sequences from the inner API. The scheduler + RabbitMQ flow demonstrates how the platform closes the loop, moving from discovery (sample & creator crawlers) to automated engagement without human-in-the-loop tweaks once the MQ payloads arrive.

## Data pipeline overview

1. Operators publish RabbitMQ jobs (typically `function: "sample"` or outreach tasks) to `crawler.direct`.
2. Playwright crawlers log into TikTok partner portals, read tab states, parse actions/logistics/promotions, and normalize each row into the schema the backend expects.
3. Normalized rows or creator/outreach payloads are POSTed to the inner API (`/samples/ingest`, `/creators/ingest`, `/outreach_tasks/ingest`), with `X-INFound-Inner-Service-Token` headers validated by `RequestFilterMiddleware`.
4. The inner API upserts MySQL tables, writes `sample_chatbot_schedules`, and publishes chatbot jobs via `RabbitMQProducer` to `chatbot.topic` with routing keys like `chatbot.sample.batch` or `chatbot.outreach.batch`.
5. `sample_chatbot`/`outreach_chatbot`/`unified_chatbot` consume those jobs, launch Playwright sessions, and send the prepared message sequences; failures go to DLQs for manual or scripted re-processing.

## Getting started

### Backend services

```bash
cd infound-backend-services
poetry install
export SERVICE_NAME=portal_inner_open_api
export ENV=dev
poetry run python main.py
```

- Switch `SERVICE_NAME` to `portal_creator_open_api` or other services to run additional FastAPI apps.
- Override `configs/base.yaml` placeholders by creating environment-specific YAML files or by setting environment variables (e.g., `MYSQL_HOST`, `RABBITMQ__PASSWORD`, `AUTH__VALID_TOKENS`).

### Data collection services

```bash
cd infound-data-collection
poetry install --no-root
poetry run playwright install
export SERVICE_NAME=portal_tiktok_sample_crawler_html
export ENV=dev
poetry run python main.py --consumer portal_tiktok_sample_crawler_html --env "$ENV"
```

- Swap `SERVICE_NAME`/`--consumer` to run `portal_tiktok_campaign_crawler`, `portal_tiktok_creator_crawler`, `sample_chatbot`, `outreach_chatbot`, or `unified_chatbot`.
- Playwright credentials, Gmail app passwords, and RabbitMQ/inner API hosts are loaded through environment variables or local YAML overrides (see `common/core/config.py` for aliasing rules).
- Replace every `<...>` placeholder in the YAML configs with real values before deploying (RabbitMQ hosts, MySQL credentials, inner API tokens, etc.).

## Startup checklist (committee demo)

### Sample crawler (Playwright HTML version)

```bash
cd infound-data-collection
export SERVICE_NAME=portal_tiktok_sample_crawler_html
export ENV=dev
export PLAYWRIGHT_HEADLESS=false
poetry run python main.py --consumer portal_tiktok_sample_crawler_html --env "$ENV"
```

### Campaign crawler

```bash
cd infound-data-collection
export SERVICE_NAME=portal_tiktok_campaign_crawler
export ENV=dev
export PLAYWRIGHT_HEADLESS=false
poetry run python main.py --consumer portal_tiktok_campaign_crawler --env "$ENV"
```

### Creator crawler

```bash
cd infound-data-collection
export SERVICE_NAME=portal_tiktok_creator_crawler
export ENV=dev
export PLAYWRIGHT_HEADLESS=false
poetry run python main.py --consumer portal_tiktok_creator_crawler --env "$ENV"
```

### Sample chatbot

```bash
cd infound-data-collection
export SERVICE_NAME=sample_chatbot
export ENV=dev
poetry run python main.py --consumer sample_chatbot --env "$ENV"
```

### Outreach chatbot

```bash
cd infound-data-collection
export SERVICE_NAME=outreach_chatbot
export ENV=dev
poetry run python main.py --consumer outreach_chatbot --env "$ENV"
```

### Unified chatbot (sample + outreach)

```bash
cd infound-data-collection
export SERVICE_NAME=unified_chatbot
export ENV=dev
poetry run python main.py --consumer unified_chatbot --env "$ENV"
```

## Security & sanitization

This presentation copy removes all secrets: IP addresses, hostnames, tokens, Gmail credentials, and passwords are shown as `<PLACEHOLDER>` or `example.com` domains. Treat the placeholders in every YAML (`infound-backend-services/configs/base.yaml`, `infound-data-collection/configs/base.yaml`, etc.) as prompts to load production values from a secure store before running.

## Additional pointers

- Refer to `infound-backend-services/readme.md` for detailed sample ingestion contracts, chatbot scheduling, creator/outreach APIs, and SQL model generation guidance.
- Refer to `infound-data-collection/readme.md` for consumer configuration, RabbitMQ routing keys, Playwright behavior, data exports, and chatbot/creator crawler operations.
