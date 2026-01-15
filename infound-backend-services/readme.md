# Project Overview

This repository contains the backend services for the INFound project. It is built with Python 3.13.

# Project Structure

```plaintext
infound-backend-services/
|-- apps/
|   |-- portal_inner_open_api/   # Internal service-only API
|   |   |-- api/                 # Service routes
|   |   |   |-- __init__.py
|   |   |   |-- endpoints/       # Service endpoints
|   |   |   |-- router.py        # Service router
|   |   |-- configs/             # Service configs (YAML)
|   |   |   |-- dev.yaml         # Service dev config (YAML, can override global)
|   |   |-- models/              # Service data models
|   |   |   |-- __init__.py
|   |   |   `-- user_models.py
|   |   `-- services/            # Service business logic
|   |       |-- __init__.py
|   |       |-- user_service.py
|   |       `-- startup.py       # Service startup hooks
|   `-- portal_creator_open_api/ # Creator-side API service
|-- common/                      # Shared modules (base services/libs, maintained separately)
|   |-- __init__.py
|   |-- core/                    # Shared core components
|   |   |-- config.py            # Multi-env config (supports per-service overrides)
|   |   |-- exceptions.py        # Global exception handling (standard response)
|   |   |-- logger.py            # Logging config (standard format, per-service logs)
|   |   |-- dependencies.py      # DI (Redis/JWT shared)
|   |   `-- response.py          # Unified API response format
|   |-- models/                  # Shared models (JWT payloads, common request/response)
|   |   |-- __init__.py
|   |   |-- common_request.py    # Common request models (pagination, sorting)
|   |   `-- common_response.py   # Common response models
|   |-- services/                # Shared services (Redis, third-party APIs)
|   |   |-- __init__.py
|   |   `-- redis_service.py     # Shared Redis helpers
|   `-- utils/                   # Shared utilities (JWT, crypto, date helpers)
|       |-- __init__.py
|       `-- jwt_utils.py
|-- configs/                     # Multi-env config (supports per-service overrides)
|   `-- base.yaml                # Global base config (YAML, shared by all services)
|-- pyproject.toml               # Unified dependencies (shared + app)
|-- Dockerfile                   # Base Dockerfile (build a single service)
`-- main.py                      # Unified entry, loads service hooks
```

# Development Setup

## 1. Install Python 3.13.*

## 2. Install Poetry

Poetry recommends the install script (instead of pip) to avoid dependency conflicts.

### Linux / macOS

#### Option 1: Official script (recommended)

```bash
# Default install path: ~/.local/share/pypoetry
curl -sSL https://install.python-poetry.org | python3 -

# Add to PATH (temporary)
export PATH="$HOME/.local/bin:$PATH"

# Add to PATH (permanent)
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

#### Option 2: Custom install directory

```bash
# 1. Set custom directory
export POETRY_HOME="/opt/poetry"  # Change to your path

# 2. Install (respects POETRY_HOME)
curl -sSL https://install.python-poetry.org | python3 -

# 3. Add to PATH
export PATH="$POETRY_HOME/bin:$PATH"

# 4. Make it persistent
echo 'export POETRY_HOME="/opt/poetry"' >> ~/.bashrc
echo 'export PATH="$POETRY_HOME/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

### Windows

#### Option 1: PowerShell one-liner

```powershell
# Default install path: %APPDATA%\Python\Scripts
(Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | py -

# Add the following path to PATH:
# %APPDATA%\Python\Scripts
# Example: C:\Users\<your-user>\AppData\Roaming\Python\Scripts
```

#### Option 2: Custom directory

```powershell
# 1. Set environment variable (System Properties -> Advanced -> Environment Variables)
#    Name: POETRY_HOME
#    Value: D:\tools\poetry  (your custom path)

# 2. Install
(Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | py -

# 3. Add %POETRY_HOME%\bin to PATH
#    Example: D:\tools\poetry\bin

# 4. Restart the terminal to verify
```

### Verify installation

```bash
poetry --version
# Output: Poetry (version 1.8.x)
```

### Optional mirror configuration (Tsinghua)

#### Temporary

```bash
export POETRY_PYPI_MIRROR="https://pypi.tuna.tsinghua.edu.cn/simple"
```

#### Persistent (recommended)

```bash
# Add Poetry mirror
poetry source add --priority primary tuna https://pypi.tuna.tsinghua.edu.cn/simple

# Show config
poetry config --list
```

#### Configure pip mirror (used by Poetry install)

```bash
# Linux/macOS
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

# Windows
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

### Common local config

```bash
# Create .venv in project root (IDE friendly)
poetry config virtualenvs.in-project true --local

# Auto-create virtualenv
poetry config virtualenvs.create true

# Show current config
poetry config --list
```

### Troubleshooting

| Issue                          | Fix                                                         |
|-------------------------------|--------------------------------------------------------------|
| poetry: command not found     | PATH not set correctly. Add the install path to PATH.        |
| Install script fails          | Check Python version (3.8+). Ensure network access.          |
| Windows permission error      | Run PowerShell as admin or use pipx.                         |
| CI/CD install is slow         | Use pip with a pinned version: pip install poetry==1.8.0     |

### Project structure after install

```bash
# Create new project
poetry new myproject
cd myproject

# Or initialize an existing project
poetry init  # interactive pyproject.toml

# Install dependencies
poetry add requests
poetry add --group dev pytest

# Enter virtualenv
poetry shell

# Run a command
poetry run python main.py
```

Recommended: Open the project in PyCharm so it can detect the Poetry environment.

## 3. Run poetry install at repo root

# Generate ORM models from database tables

```bash
sqlacodegen mysql+pymysql://<MYSQL_USER>:<MYSQL_PASSWORD>@<MYSQL_HOST>:<MYSQL_PORT>/<MYSQL_DB> --outfile common/models/infound.py
```

# Sample ingestion API (Collector -> Inner API)

The Playwright crawler no longer writes to the database directly. The
`portal_tiktok_sample_crawler` posts normalized row arrays to the inner API,
which validates and writes to `samples` / `sample_contents` / `sample_crawl_logs`.
Key modules:

1. `apps/portal_inner_open_api/services/sample_ingestion_service.py`: wraps
   `SampleIngestionService`, implements `_build_*payload`,
   `_build_content_summary_map`, `_logistics_summary_entries`, `_upsert_sample*`,
   and writes directly to `common.models.infound`.
2. `apps/portal_inner_open_api/models/sample.py`: defines Pydantic models
   `sampleRow`, `sampleIngestionOptions`, `sampleIngestionRequest`,
   `sampleIngestionResult`, etc. Request/response fields use lower camelCase.
3. `apps/portal_inner_open_api/apis/endpoints/sample.py`: exposes
   `POST /samples/ingest` and mounts it in `apis/router.py`. The handler depends
   on `SampleIngestionService` and uses `DatabaseManager.get_session()`.
4. `startup.py` runs `DatabaseManager.initialize()` in `startup_hook` to prepare
   the MySQL pool on API startup.

Additionally, the inner API writes schedules into `sample_chatbot_schedules`
from the latest `samples` snapshot (status changes + reminder repeats). A
`ChatbotSchedulePublisher` background task polls due schedules and publishes
batches to RabbitMQ. The data collection side `sample_chatbot` only consumes MQ
and sends messages (no template or scenario management).

### Chatbot message delivery API (Inner API -> MQ)

- Method and path: `POST /chatbot/messages`
- Auth: same as other inner API endpoints (`X-INFound-Inner-Service-Token`)
- Request body: JSON array, each item must include `platformCreatorId` and
  `messages` (`[{type, content, meta?}, ...]`)
- Response: `success_response({"count": <task_count>})`

### API contract

- Method and path: `POST /samples/ingest`
- Auth: `RequestFilterMiddleware`. Collector must send
  `X-INFound-Inner-Service-Token`, token comes from
  `apps/portal_inner_open_api/configs/base.yaml` -> `AUTH.VALID_TOKENS`.
- Request body:
  - `source`: string, data source (for example `portal_tiktok_sample_crawler`)
  - `operatorId`: UUID from collector via `SAMPLE_DEFAULT_OPERATOR_ID`
  - `options`: MQ context (`campaignId`, `tabs`, `region`, `scanAllPages`,
    `expandViewContent`, `viewLogistics`, `exportExcel`, etc) for audit
  - `rows`: normalized row array, same structure as `_persist_results`
    (fields include `region`, `productName`, `platformProductId`, `status`,
    `requestTimeRemaining`, `platformCreator*`, `postRate`, `isShowcase`,
    `contentSummary` / `logisticsSnapshot`, plus promotion metrics when
    `type` is `video` or `live`)
- Response: `success_response({"inserted": <rows>, "products": <unique_products>})`.
  Validation or DB errors return standardized errors and are logged.

### Request example

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

The inner API groups rows by `platform_product_id` and upserts `samples` and
`sample_contents`, then writes `sample_crawl_logs` / `sample_content_crawl_logs`.
The logic matches the collector's original `_persist_results`.

---

## Creator Outreach

Inner API provides outreach tasks, creator ingestion, and message dispatch APIs
for the data collection outreach crawler.

### 1) Creator ingestion API (Crawler -> Inner API)

- Method and path: `POST /creators/ingest`
- Auth: `X-INFound-Inner-Service-Token`
- Request body:
  - `source`: data source (for example `portal_tiktok_creator_crawler`)
  - `operatorId`: account/operator UUID (for audit)
  - `options`: task context (`taskId`, `searchStrategy`, `brandName`, etc)
  - `rows`: creator data array (`platformCreatorId`,
    `platformCreatorDisplayName`, `platformCreatorUsername`, `connect`, `reply`,
    `send`, `whatsapp`, `email`, etc)
- Tables: `creators`, `creator_crawl_logs`

### 2) Outreach task sync API (Crawler -> Inner API)

- Method and path: `POST /outreach_tasks/ingest`
- Auth: `X-INFound-Inner-Service-Token`
- Request body (lower camelCase; `task` can include extra fields):
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
- Tables: `outreach_tasks`

### 3) Message dispatch API (Inner API -> MQ)

- Method and path: `POST /chatbot/messages`
- Auth: `X-INFound-Inner-Service-Token`
- Request body: task array (each item must include `platformCreatorId` and
  `messages`)
- MQ: inner API uses `RabbitMQProducer` to publish to `chatbot.topic` with routing
  key `chatbot.sample.batch`. `sample_chatbot` consumes and sends.

# Code Conventions

## 1. Naming

| Type          | Convention            | Example                  |
|---------------|-----------------------|--------------------------|
| Module/Package| lowercase_with_underscores | `import my_module`   |
| Class         | PascalCase            | `class MyClass:`         |
| Function/Var  | lowercase_with_underscores | `def calculate_area()`|
| Constant      | UPPERCASE_WITH_UNDERSCORES | `MAX_CONNECTIONS = 100` |
| Private attr  | __leading_double_underscore | `__private_var`  |
| Protected attr| _leading_single_underscore | `_protected_var`  |

## 2. Imports

1. Location: top of file, after module comments/docstrings
2. Order: three groups with a blank line between
   - Standard library
   - Third-party libraries
   - Local modules
3. Sort alphabetically within each group

```python
# Correct
import os
import sys

import numpy as np
import requests

from myproject import config
from myproject.utils import helper
```

---

## 3. Comments and docstrings

### 1. Block comments

- Use `#` plus a space, aligned with code indentation
- Explain why, not what

```python
# Wrong: repeats the code
# Right: explain why for better precision
area = pi * radius ** 2
```

### 2. Docstrings

- Use triple quotes `"""..."""` or `'''...'''`
- First statement in module/function/class/method
- Include purpose, args, return value, and exceptions

```python
def calculate_area(radius):
    """Calculate area of a circle.

    Args:
        radius: Radius of the circle (float)

    Returns:
        float: Area of the circle
    """
    return 3.14159 * radius ** 2
```

---

## 4. Other guidelines

1. String quotes: single or double is fine, but be consistent
2. Boolean checks: use `if x:` instead of `if x == True:`
3. Exceptions: catch specific exceptions, avoid bare `except:`
4. Encoding: Python 3 defaults to UTF-8; no file header needed
