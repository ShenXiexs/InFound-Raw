# INFound Backend Services

This repository hosts the FastAPI backend services for the INFound platform. It is organized as a multi-service Python project with shared infrastructure (configuration, logging, database access, Redis, and RabbitMQ).

## Key Services

- `portal_inner_open_api`: internal API for data ingestion and chatbot scheduling.
- `portal_creator_open_api`: creator-facing API for login and sample workflows.
- `common`: shared core utilities and service clients used by both APIs.

## Repository Structure

```text
infound-backend-services/
├── apps/
│   ├── portal_creator_open_api/
│   │   ├── apis/
│   │   ├── configs/
│   │   ├── middlewares/
│   │   └── services/
│   └── portal_inner_open_api/
│       ├── apis/
│       ├── configs/
│       ├── models/
│       └── services/
├── common/
│   ├── core/
│   ├── models/
│   └── services/
├── configs/
│   └── base.yaml
├── Dockerfile
├── main.py
└── pyproject.toml
```

## Requirements

- Python 3.13
- Poetry

## Quick Start

```bash
# install dependencies
poetry install

# select service and environment
export SERVICE_NAME=portal_inner_open_api
export ENV=dev

# run
poetry run python main.py
```

## Configuration

Configuration is loaded in this order:

1. `configs/base.yaml`
2. `apps/<service>/configs/base.yaml`
3. `apps/<service>/configs/<env>.yaml`
4. Environment variables (use `__` to override nested keys)

Sensitive values are intentionally placeholders and must be supplied via environment variables or local overrides:

- `JWT_SECRET_KEY`
- `MYSQL_*`
- `REDIS_*`
- `RABBITMQ_*`
- `AUTH.VALID_TOKENS` (inner API token list)

Example override:

```bash
export MYSQL__HOST=localhost
export MYSQL__USER=app_user
export MYSQL__PASSWORD=app_password
export MYSQL__DB=infound_db
```

## Sample Ingestion Flow (Collector -> Inner API)

The Playwright collector posts normalized rows to the inner API, which validates and upserts into `samples`, `sample_contents`, and related tables. Key modules:

1. `apps/portal_inner_open_api/services/sample_ingestion_service.py`: orchestration and upserts.
2. `apps/portal_inner_open_api/models/sample.py`: Pydantic request/response models.
3. `apps/portal_inner_open_api/apis/endpoints/sample.py`: `POST /samples/ingest` endpoint.
4. `apps/portal_inner_open_api/startup.py`: initializes the DB session pool.

## Chatbot Dispatch (Inner API -> MQ)

The inner API detects sample state changes, writes schedules to `sample_chatbot_schedules`, and publishes tasks to RabbitMQ. The data-collection service (`sample_chatbot`) consumes those tasks and sends messages via Playwright.

## API Example: `POST /samples/ingest`

```http
POST /samples/ingest HTTP/1.1
Host: inner-api.example.com
X-INFound-Inner-Service-Token: <INNER_API_TOKEN>
Content-Type: application/json

{
  "source": "portal_tiktok_sample_crawler",
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
  "rows": [
    {
      "region": "MX",
      "productName": "Sample Tee",
      "platformProductId": "1234567890",
      "platformCampaignId": "7563877506852587284",
      "platformCampaignName": "Holiday Sample",
      "status": "completed",
      "requestTimeRemaining": "0 days",
      "platformCreatorDisplayName": "Creator MX",
      "platformCreatorUsername": "@creator",
      "creatorUrl": "https://tiktok.com/@creator/video/123",
      "stock": 10,
      "availableSampleCount": 3,
      "isShowcase": true,
      "postRate": "0.54",
      "actions": [{"label": "View content", "enabled": true}],
      "actionDetails": {"view_content": {"video": 1, "live": 0}},
      "type": "video",
      "typeNumber": "2",
      "promotionName": "Spark Ads",
      "promotionTime": "2024-12-12",
      "promotionViewCount": 2000,
      "promotionLikeCount": 150,
      "promotionCommentCount": 20,
      "promotionOrderCount": 5,
      "promotionOrderTotalAmount": "120.50",
      "logisticsSnapshot": {
        "basic_info": [{"label": "Carrier", "value": "DHL"}],
        "timeline": [{"title": "Delivered", "time": "2024-12-15"}]
      }
    }
  ]
}
```

## ORM Model Generation (Optional)

```bash
sqlacodegen \
  mysql+pymysql://<DB_USER>:<DB_PASSWORD>@<DB_HOST>:<DB_PORT>/<DB_NAME> \
  --outfile common/models/infound.py
```

## Code Style Notes

- Use snake_case for modules/functions and PascalCase for classes.
- Group imports: standard library, third-party, local.
- Prefer explicit exception types over bare `except:`.
- Keep docstrings concise and focused on intent.
