# INFound Influencer Platform (Backend + Data Collection)

This workspace contains two coordinated Python projects that power the INFound influencer data pipeline:

- `infound-backend-services`: FastAPI services for internal ingestion and creator-facing APIs.
- `infound-data-collection`: Playwright + RabbitMQ consumers that crawl, normalize, and dispatch messages.

## How the Pieces Fit Together

1. The crawler consumes MQ tasks and normalizes sample rows.
2. The collector posts rows to the inner API (`/samples/ingest`).
3. The inner API upserts into MySQL and writes chatbot schedules.
4. The inner API publishes MQ tasks for outbound chat.
5. The chatbot consumer sends messages via Playwright.

## Repositories

### Backend Services

Path: `infound-backend-services`

- Internal API: ingestion + chatbot scheduling.
- Creator API: login and sample endpoints.
- Shared modules: config, logging, DB, Redis, RabbitMQ producer.

See: `infound-backend-services/readme.md`

### Data Collection

Path: `infound-data-collection`

- Sample crawler consumer (Playwright + MQ).
- Chatbot dispatcher consumer.
- Shared MQ and config infrastructure.

See: `infound-data-collection/readme.md`

## Security Notes

All tokens, credentials, and internal addresses have been replaced with placeholders. Configure sensitive values via environment variables or local overrides; do not commit secrets to source control.

## Quick Start (Local)

```bash
# backend
cd infound-backend-services
poetry install
export SERVICE_NAME=portal_inner_open_api
export ENV=dev
poetry run python main.py

# data collection
cd ../infound-data-collection
poetry install --no-root
export CONSUMER=portal_tiktok_sample_crawler
export ENV=dev
poetry run python main.py --consumer "$CONSUMER" --env "$ENV"
```

Replace values in configs and env vars with your local credentials.
