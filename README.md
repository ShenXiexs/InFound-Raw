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
- `apps/portal_tiktok_creator_crawler` gathers creator metadata, contact info, and outreach-relevant stats, then posts them to the inner API endpoints for creator ingestion, outreach task syncing, and chatbot scheduling.
- `apps/sample_chatbot`, `apps/outreach_chatbot`, and `apps/unified_chatbot` consume the `chatbot.topic` exchange, respect DLQs, and use Playwright instances to send sample and outreach messages, while providing manual overrides for accounts/regions and retry limits.
- RabbitMQ tasks are routed through `crawler.direct`, `chatbot.topic`, and their DLQs; each consumer can also be run with `AT_MOST_ONCE` semantics or batched delivery and can export normalized rows to `data/manage_sample/` when `exportExcel` is enabled.

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

- Swap `SERVICE_NAME`/`--consumer` to run `portal_tiktok_creator_crawler`, `sample_chatbot`, `outreach_chatbot`, or `unified_chatbot`.
- Playwright credentials, Gmail app passwords, and RabbitMQ/inner API hosts are loaded through environment variables or local YAML overrides (see `common/core/config.py` for aliasing rules).
- Replace every `<...>` placeholder in the YAML configs with real values before deploying (RabbitMQ hosts, MySQL credentials, inner API tokens, etc.).

## Security & sanitization

This presentation copy removes all secrets: IP addresses, hostnames, tokens, Gmail credentials, and passwords are shown as `<PLACEHOLDER>` or `example.com` domains. Treat the placeholders in every YAML (`infound-backend-services/configs/base.yaml`, `infound-data-collection/configs/base.yaml`, etc.) as prompts to load production values from a secure store before running.

## Additional pointers

- Refer to `infound-backend-services/readme.md` for detailed sample ingestion contracts, chatbot scheduling, creator/outreach APIs, and SQL model generation guidance.
- Refer to `infound-data-collection/readme.md` for consumer configuration, RabbitMQ routing keys, Playwright behavior, data exports, and chatbot/creator crawler operations.
