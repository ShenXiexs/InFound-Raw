# 项目介绍

此项目为 INFound 项目的后端服务工程项目，以 Python 技术栈实现，运行环境为 Python 3.13

# 项目目录结构

```plaintext
infound-backend-services/
├── apps/
│   ├── portal_inner_open_api/   # 内部服务专属 API，只对内部服务使用
│   │   ├── api/                 # 服务专属路由
│   │   │   ├── __init__.py
│   │   │   ├── endpoints/       # 服务专属接口
│   │   │   ├── router.py        # 服务专属路由
│   │   ├── configs/             # 服务专属配置（YAML）
│   │   │   ├── dev.yaml         # 服务开发环境专属配置（YAML，可覆盖全局配置）
│   │   ├── models/              # 服务专属数据模型
│   │   │   ├── __init__.py
│   │   │   └── user_models.py
│   │   └── services/            # 服务专属业务逻辑
│   │      ├── __init__.py
│   │      └── user_service.py
│   │      └── startup.py        # 服务专属启动逻辑
│   ├── portal_creator_open_api/ # 达人端专属 API 服务
├── common/                      # 公共模块（共用基础服务/类库，独立维护）
│   ├── __init__.py
│   ├── core/                    # 共用核心组件
│   │   ├── config.py            # 多环境配置（支持服务A/B独立配置）
│   │   ├── exceptions.py        # 全局异常捕获（统一响应格式）
│   │   ├── logger.py            # 日志配置（统一格式，支持独立日志文件）
│   │   ├── dependencies.py      # 依赖注入（Redis/JWT 共用）
│   │   └── response.py          # 统一 API 返回格式
│   ├── models/                  # 共用数据模型（如 JWT 载荷、公共请求/响应模型）
│   │   ├── __init__.py
│   │   ├── common_request.py    # 共用请求模型（如分页、排序）
│   │   └── common_response.py   # 共用响应模型
│   ├── services/                # 共用业务服务（如 Redis 操作、第三方 API 调用）
│   │   ├── __init__.py
│   │   └── redis_service.py     # 共用 Redis 工具类
│   └── utils/                   # 共用工具函数（如 JWT、加密、日期处理）
│       ├── __init__.py
│       └── jwt_utils.py
├── configs/                     # 多环境配置（支持服务A/B独立配置）
│   ├── base.yaml                # 全局基础配置（YAML 格式，所有服务共用，不变）
├── pyproject.toml               # 统一依赖清单（公共+业务依赖）
├── Dockerfile                   # 基础 Dockerfile（支持构建单个服务）
├── main.py                      # 统一入口 main.py 动态调用专属钩子
```

# 开发环境准备

## 1. 安装 Python 3.13.*

## 2. 安装 Poetry

Poetry 官方推荐使用**安装脚本**，而非 pip，以避免依赖冲突。提供跨平台命令和配置。

### 🐧 **Linux / macOS 安装**

#### **方式一：官方脚本（推荐）**

```bash
# 默认安装到 ~/.local/share/pypoetry
curl -sSL https://install.python-poetry.org | python3 -

# 添加到 PATH（临时）
export PATH="$HOME/.local/bin:$PATH"

# 永久生效（推荐）
echo 'export PATH="$HOME/.local/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

#### **方式二：指定安装目录**

```bash
# 1. 设置自定义目录
export POETRY_HOME="/opt/poetry"  # 可改为你的路径

# 2. 执行安装（自动识别 POETRY_HOME）
curl -sSL https://install.python-poetry.org | python3 -

# 3. 添加到 PATH
export PATH="$POETRY_HOME/bin:$PATH"

# 4. 永久生效
echo 'export POETRY_HOME="/opt/poetry"' >> ~/.bashrc
echo 'export PATH="$POETRY_HOME/bin:$PATH"' >> ~/.bashrc
source ~/.bashrc
```

---

### 🪟 **Windows 安装**

#### **方式一：PowerShell 一键安装**

```powershell
# 默认安装到 %APPDATA%\Python\Scripts
(Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | py -

# 手动将以下路径添加到系统环境变量 PATH
# %APPDATA%\Python\Scripts
# 例如: C:\Users\<你的用户名>\AppData\Roaming\Python\Scripts
```

#### **方式二：指定目录安装**

```powershell
# 1. 设置环境变量（右键"此电脑"→属性→高级系统设置→环境变量）
#    变量名: POETRY_HOME
#    变量值: D:\tools\poetry  （你的自定义路径）

# 2. 执行安装
(Invoke-WebRequest -Uri https://install.python-poetry.org -UseBasicParsing).Content | py -

# 3. 将 %POETRY_HOME%\bin 添加到系统 PATH
#    例如: D:\tools\poetry\bin

# 4. 重启终端验证
```

---

### ✅ **验证安装**

```bash
poetry --version
# 输出: Poetry (version 1.8.x)
```

---

### 🚀 **国内加速配置（清华源）**

#### **临时生效**

```bash
export POETRY_PYPI_MIRROR="https://pypi.tuna.tsinghua.edu.cn/simple"
```

#### **永久配置（推荐）**

```bash
# 添加 Poetry 镜像源
poetry source add --priority primary tuna https://pypi.tuna.tsinghua.edu.cn/simple

# 查看配置
poetry config --list
```

#### **配置 PIP 镜像（ Poetry 安装包时会用到）**

```bash
# Linux/macOS
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple

# Windows
pip config set global.index-url https://pypi.tuna.tsinghua.edu.cn/simple
```

---

### 🎨 **常用初始化配置**

```bash
# 在项目目录内创建 .venv（便于 IDE 识别）
poetry config virtualenvs.in-project true --local

# 自动创建虚拟环境
poetry config virtualenvs.create true

# 查看当前配置
poetry config --list
```

---

### ⚠️ **常见问题**

| 问题                            | 解决方案                                       |
|-------------------------------|--------------------------------------------|
| **poetry: command not found** | 未正确配置 PATH，检查安装路径并添加到环境变量                  |
| **安装脚本执行失败**                  | 检查 Python 版本（需 3.8+），确保网络通畅，或使用镜像          |
| **Windows 权限错误**              | 以管理员身份运行 PowerShell，或改用 pipx 安装            |
| **CI/CD 环境安装慢**               | 使用 pip 安装并指定版本：`pip install poetry==1.8.0` |

---

### 📁 **安装后项目结构**

```bash
# 创建新项目
poetry new myproject
cd myproject

# 或初始化现有项目
poetry init  # 交互式填写 pyproject.toml

# 安装依赖
poetry add requests
poetry add --group dev pytest

# 进入虚拟环境
poetry shell

# 运行命令
poetry run python main.py
```

**推荐**：在 PyCharm 中打开项目，它会自动识别 Poetry 环境并提示配置解释器。

---

## 3. 根目录执行 poetry install

# 数据库表自动生成 ORM 模型文件

```bash
sqlacodegen mysql+pymysql://infound-pro:J6B%5Etu%29E%7E%24HJBb@47.238.5.253:8801/infound.pro --outfile common/models/infound.py
```

## Sample 数据入库 API（Collector → Inner API）

Playwright 爬虫现已不直接写入数据库，`portal_tiktok_sample_crawler` 会把标准化后的行数组提交到 inner API，由后者统一校验并入库 `samples`/`sample_contents`/`sample_crawl_logs`。关键模块包括：

1. `apps/portal_inner_open_api/services/sample_ingestion_service.py`：封装 `SampleIngestionService`，实现 `_build_*payload`、`_build_content_summary_map`、`_logistics_summary_entries`、`_upsert_sample*` 等逻辑，直接操作 `common.models.infound`。
2. `apps/portal_inner_open_api/models/sample.py`：定义 `sampleRow`、`sampleIngestionOptions`、`sampleIngestionRequest`、`sampleIngestionResult` 等 Pydantic 模型，约束 collector 的请求结构（请求/响应字段使用小驼峰）。
3. `apps/portal_inner_open_api/apis/endpoints/sample.py`：暴露 `POST /samples/ingest` 接口，并在 `apis/router.py` 中挂载；handler 依赖 `SampleIngestionService` 并通过 `DatabaseManager.get_session()` 获取会话。
4. `startup.py` 的 `startup_hook` 会调用 `DatabaseManager.initialize()`，确保 API 启动时即准备好 MySQL 连接池。

另外，inner API 会根据 `samples` 最新快照更新 chatbot 字段（状态变更触发 + 提醒类重复次数），并由 `ChatbotSchedulePublisher`（启动时后台任务）轮询 `samples` 表的到期记录、批量投递 RabbitMQ；消息内容由 inner API 生成/透传，数据采集侧的 `sample_chatbot` 仅负责消费 MQ 并发送（不管理模板/场景）。

### Chatbot 消息投递 API（Inner API → MQ）

- **Method & Path**：`POST /chatbot/messages`
- **鉴权**：同 inner API 其他接口（`X-INFound-Inner-Service-Token`）
- **Request Body**：JSON 数组，每项至少包含 `platformCreatorId` 与 `messages`（`[{type, content, meta?}, ...]`）
- **Response**：`success_response({"count": <task_count>})`

### API 约定

- **Method & Path**：`POST /samples/ingest`
- **鉴权**：沿用 `RequestFilterMiddleware`，collector 需要在请求头里包含 `X-INFound-Inner-Service-Token`，token 值来自 `apps/portal_inner_open_api/configs/base.yaml` 的 `AUTH.VALID_TOKENS`。
- **Request Body**
  - `source`: 字符串，标记数据来源（如 `portal_tiktok_sample_crawler`）
  - `operatorId`: UUID，由 collector 通过 `SAMPLE_DEFAULT_OPERATOR_ID` 传入
  - `options`: 对应 MQ 指令上下文（`campaignId`, `tabs`, `region`, `scanAllPages`, `expandViewContent`, `viewLogistics`, `exportExcel` 等），方便后续审计
  - `rows`: Playwright 层整理后的行数组，每一项和当前 `_persist_results` 接收到的数据结构一致（字段包含 `region`, `productName`, `platformProductId`, `status`, `requestTimeRemaining`, `platformCreator*`, `postRate`, `isShowcase`, `contentSummary`/`logisticsSnapshot`，以及当 `type` 为 `video` 或 `live` 时的推广指标）
- **Response**：统一返回 `success_response({"inserted": <rows>, "products": <unique_products>})`。若校验失败或数据库异常，返回标准化错误并写日志。

### 请求示例

```http
POST /samples/ingest HTTP/1.1
Host: inner-api.infound.ai
X-INFound-Inner-Service-Token: 844a22c4c6d47231bb4fc89c3e8a64ca5b09ec5de8f6d4bf65dacd7d
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

> Inner API 收到数组后会按照 `platform_product_id` 聚合，分别 upsert `samples` 和 `sample_contents`，并写入 `sample_crawl_logs` / `sample_content_crawl_logs`，逻辑与原 collector 中的 `_persist_results` 保持一致。

---

## 建联任务（Creator Outreach）

Inner API 提供建联任务、达人入库、消息下发三类接口，配合 data-collection 的建联爬虫使用。

### 1) 达人入库 API（Crawler → Inner API）

- **Method & Path**：`POST /creators/ingest`
- **鉴权**：`X-INFound-Inner-Service-Token`
- **Request Body**：
  - `source`: 数据来源（如 `portal_tiktok_creator_crawler`）
  - `operatorId`: 账号/操作人 UUID（用于审计字段）
  - `options`: 任务上下文（可包含 `taskId`/`searchStrategy`/`brandName` 等）
  - `rows`: 达人数据数组（包含 `platformCreatorId`/`platformCreatorDisplayName`/`platformCreatorUsername`/`connect`/`reply`/`send`/`whatsapp`/`email` 等字段）
- **写入表**：`creators`、`creator_crawl_logs`

### 2) 建联任务同步 API（Crawler → Inner API）

- **Method & Path**：`POST /outreach_tasks/ingest`
- **鉴权**：`X-INFound-Inner-Service-Token`
- **Request Body**（小驼峰；`task` 可扩展字段）：
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
- **写入表**：`outreach_tasks`

### 3) 消息下发 API（Inner API → MQ）

- **Method & Path**：`POST /chatbot/messages`
- **鉴权**：`X-INFound-Inner-Service-Token`
- **Request Body**：任务数组（每条至少含 `platformCreatorId` 与 `messages`）
- **MQ**：Inner API 通过 `RabbitMQProducer` 推送到 `chatbot.topic`，routing key 为 `chatbot.sample.batch`，由 `sample_chatbot` 消费并发送。

# 代码规范

## 1. 命名规范

| 类型        | 规范        | 示例                      |
|-----------|-----------|-------------------------|
| **模块/包**  | 小写 + 下划线  | `import my_module`      |
| **类**     | 大驼峰命名法    | `class MyClass:`        |
| **函数/变量** | 小写 + 下划线  | `def calculate_area()`  |
| **常量**    | 全大写 + 下划线 | `MAX_CONNECTIONS = 100` |
| **私有属性**  | 双下划线开头    | `__private_var`         |
| **保护属性**  | 单下划线开头    | `_protected_var`        |

## 2. 导入规范

1. **位置**：文件顶部，在模块注释和文档字符串之后
2. **顺序**：分三组，组间空1行
    - 标准库
    - 第三方库
    - 本地模块
3. **排序**：每组按字母顺序

```python
# ✅ 正确
import os
import sys

import numpy as np
import requests

from myproject import config
from myproject.utils import helper
```

---

## 3. 注释与文档字符串

### 1. 块注释

- `#` 后空1格，与代码同等级缩进
- **说明"为什么"而非"做了什么"**

```python
# 计算圆面积（错误示例：重复代码逻辑）
# 使用数学常数提高精度（正确示例：说明原因）
area = pi * radius ** 2
```

### 2. 文档字符串（Docstrings）

- **使用三引号** `"""..."""` 或 `'''...'''`
- **位置**：模块、函数、类、方法的第一个语句
- **内容**：功能、参数、返回值、异常说明

```python
def calculate_area(radius):
    """计算圆的面积。
    
    Args:
        radius: 圆的半径（浮点数）
    
    Returns:
        float: 圆的面积
    """
    return 3.14159 * radius ** 2
```

---

## 4. 其他核心建议

1. ** 字符串引号 **：单引号 `'` 和双引号 `"` 均可，但需保持统一
2. ** 布尔比较 **：直接用 `if x:` 而非 `if x == True:`
3. ** 异常处理 **：捕获具体异常，而非裸 `except:`
4. ** 编码声明 **：Python 3 默认 UTF-8，无需文件头声明
