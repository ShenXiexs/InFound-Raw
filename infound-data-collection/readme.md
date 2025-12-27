# INFound Data Collection Services

This repository contains the data collection services used by INFound to enrich creator and product data. It provides reusable RabbitMQ consumer infrastructure, Playwright crawling workflows, and a chatbot dispatcher for outbound messages.

## Key Consumers

- `portal_tiktok_sample_crawler`: Playwright crawler that pulls sample requests and submits normalized rows to the inner API.
- `sample_chatbot`: Chatbot dispatcher that consumes MQ tasks and sends messages via Playwright.

## Repository Structure

```text
infound-data-collection/
├── apps/
│   ├── portal_tiktok_sample_crawler/
│   │   ├── crawler_consumer.py
│   │   ├── services/
│   │   └── configs/{base,dev}.yaml
│   └── sample_chatbot/
│       ├── crawler_consumer.py
│       ├── services/
│       └── configs/{base,dev}.yaml
├── common/
│   ├── core/     # config, logging, DB helpers
│   ├── mq/       # RabbitMQ connection and base consumer
│   └── models/   # SQLAlchemy models (generated)
├── configs/base.yaml
├── main.py
├── rabbitmq_connect_test.py
├── tools/
└── readme.md
```

## Configuration Model

1. **Environment variables**
   - `CONSUMER` (required): which consumer to load, e.g. `portal_tiktok_sample_crawler`.
   - `ENV` (default `dev`): selects `apps/<consumer>/configs/<env>.yaml`.
   - Any nested key can be overridden using `__`, e.g. `RABBITMQ__PASSWORD=...`.
2. **Config files**
   - `configs/base.yaml`: shared defaults.
   - `apps/<consumer>/configs/base.yaml`: consumer-specific defaults.
   - `apps/<consumer>/configs/<env>.yaml`: environment overrides.
3. **Load order**
   - base -> consumer base -> consumer env -> environment variables.

Sensitive values in this repo are placeholders and must be set locally (DB, RabbitMQ, tokens, etc.).

## Quick Start

### 1. Prerequisites

- Python 3.13
- Poetry
- RabbitMQ access
- Playwright browsers (`playwright install`)

### 2. Install Dependencies

```bash
poetry env use python3.13
poetry install --no-root
poetry run playwright install
```

### 3. Run a Consumer

```bash
export CONSUMER=portal_tiktok_sample_crawler
export ENV=dev

poetry run python main.py --consumer "$CONSUMER" --env "$ENV"
```

## RabbitMQ Integration

`common.mq` provides a robust connection and consumer base:

- Declares a direct or topic exchange plus DLX/DLQ.
- Supports QoS, retry policies, and at-most-once mode.
- Logs binding and backlog information for debugging.

## Collector -> Inner API Flow

The crawler submits normalized rows to the inner API via `SampleIngestionClient`:

- `apps/portal_tiktok_sample_crawler/services/sample_ingestion_client.py` handles HTTP calls and auth.
- Config is provided under `INNER_API` and `INNER_API_AUTH` in the consumer config.

Sample config (placeholders):

```yaml
INNER_API:
  BASE_URL: "https://inner-api.example.com"
  SAMPLE_PATH: "/samples/ingest"
  TIMEOUT: 30
INNER_API_AUTH:
  REQUIRED_HEADER: "X-INFound-Inner-Service-Token"
  VALID_TOKENS: ["<INNER_API_TOKEN>"]
```

## Sample MQ Message

```json
{
  "function": "sample",
  "tab": "completed",
  "region": "MX",
  "campaignId": "7563877506852587284",
  "scanAllPages": true,
  "expandViewContent": true,
  "viewLogistics": true,
  "exportExcel": false
}
```

Completed vs. other tabs are routed to separate queues if configured.

## Sample Chatbot Consumer

`sample_chatbot` consumes MQ tasks and sends messages via Playwright. Task payloads support both batch and single-message formats. The consumer is intentionally stateless: message content is produced upstream and forwarded as-is.

## Account Configuration

Sample login accounts are stored in `configs/accounts.json` (placeholders only). If the file is missing, the crawler can fall back to values from the consumer config.

## Tools

- `rabbitmq_connect_test.py`: quick connectivity test for RabbitMQ.
- `tools/send_test_message.py`: publish a sample MQ message using the same config.

## Development Workflow

- Format: `poetry run black .`
- Lint: `poetry run flake8`
- Add deps: `poetry add <package>`
