# INFound 后端服务项目开发文档

## 📋 项目概述

**INFound Backend Services** 是一个基于 Python 3.13 + FastAPI 构建的微服务集群系统，采用 UV
作为包管理工具，提供达人管理、样品管理、外联任务、消息推送等核心业务功能。

### 技术栈

- **运行环境**: Python 3.13+
- **包管理**: UV (现代化 Python 包管理器)
- **Web 框架**: FastAPI 0.135+
- **数据库**: MySQL (通过 SQLAlchemy 2.0 + aiomysql)
- **缓存/消息队列**: Redis, RabbitMQ
- **部署方式**: Docker + Gunicorn + Uvicorn Worker

---

## 🏗️ 项目架构

### 整体目录结构

```
infound-backend-services/
├── apps/ # 应用服务层（6 个独立服务）
│ ├── portal_creator_open_api/ # 达人端开放 API 服务
│ ├── portal_inner_open_api/ # 内部服务专属 API
│ ├── portal_operation_open_api/ # 运营端开放 API 服务
│ ├── portal_webhook_open_api/ # Webhook 回调服务
│ ├── portal_mqconsummers/ # 消息队列消费者服务
│ └── portal_async_scheduler/ # 异步任务调度服务
│
├── packages/ # 核心共享包（7 个可复用模块）
│ ├── core_base/ # 基础核心组件（配置、日志）
│ ├── core_web/ # Web 相关核心组件
│ ├── core_mq/ # 消息队列核心组件
│ ├── core_redis/ # Redis 客户端核心组件
│ ├── shared_domain/ # 领域层共享（数据库模型、ORM）
│ ├── shared_application_services/ # 应用服务层共享
│ └── shared_infrastructure/ # 基础设施层共享（认证、设置）
│  
├── logs/ # 日志文件目录
├── backup/ # 备份目录（旧版本代码）
├── pyproject.toml # UV Workspace 根配置 └── uv.lock # 依赖锁定文件
```

---

## 🎯 服务介绍

### 1. Portal Creator Open API (`portal_creator_open_api`)

**功能定位**: 面向达人端用户的开放 API 接口

**核心依赖**:

- `core-base`, `core-web`, `core-mq`, `core-redis`
- `shared-domain`, `shared-application-services`, `shared-infrastructure`
- `gunicorn`, `uvicorn`, `pyjwt`

**主要接口**:

- `apis/endpoints/account.py` - 账号管理相关接口
- `apis/endpoints/home.py` - 首页数据接口
- `apis/endpoints/sample.py` - 样品管理接口

**启动配置**:

```
# 初始化组件
- SettingsFactory (配置管理)
- RedisClientManager (Redis 连接池)
- DatabaseManager (MySQL 连接池)
- TokenManager (JWT Token 管理)
- AuthFilterMiddleware (认证中间件)
```

---

### 2. Portal Inner Open API (`portal_inner_open_api`)

**功能定位**: 内部服务专用 API，不对外暴露，供爬虫、数据采集等内部系统调用

**核心功能**:

- **样品数据入库** (`POST /samples/ingest`)
- **达人数据入库** (`POST /creators/ingest`)
- **外联任务同步** (`POST /outreach_tasks/ingest`)
- **Chatbot 消息投递** (`POST /chatbot/messages`)
- **Campaign 管理**
- **外联创作者管理** (`outreach_creator`)
- **外联任务管理** (`outreach_task`)

**特色组件**:

- `RabbitMQProducer` - RabbitMQ 消息生产者
- `RequestFilterMiddleware` - 请求过滤中间件（基于 Token 认证）
- `chatbot_schedule_publisher` - Chatbot 定时任务发布器

**认证方式**:

- 请求头 `X-INFound-Inner-Service-Token`
- Token 配置在 `configs/base.yaml` 的 `AUTH.VALID_TOKENS`

**数据模型**:

- `models/campaign.py` - Campaign 活动模型
- `models/chatbot.py` - Chatbot 消息模型
- `models/creator.py` - 达人数据模型（含 Pydantic DTO）
- `models/outreach_creator.py` - 外联达人模型
- `models/outreach_task.py` - 外联任务模型
- `models/sample.py` - 样品数据模型

---

### 3. Portal Operation Open API (`portal_operation_open_api`)

**功能定位**: 面向运营人员的后台管理 API

**核心接口**:

- `apis/endpoints/auth.py` - 认证授权接口
- `apis/endpoints/crawler_task.py` - 爬虫任务管理
- `apis/endpoints/home.py` - 运营数据看板
- `apis/endpoints/outreach_task.py` - 外联任务管理

**依赖组件**:

- `bcrypt` - 密码加密
- `RabbitMQProducer` - 消息队列
- `TokenManager` - JWT Token 管理
- `AuthFilterMiddleware` - 认证中间件

---

### 4. Portal Webhook Open API (`portal_webhook_open_api`)

**功能定位**: 第三方 Webhook 回调处理服务

**状态**: 待完善（README 为空）

---

### 5. Portal MQ Consumers (`portal_mqconsummers`)

**功能定位**: 消息队列消费者服务，处理异步任务

**状态**: 待完善（README 为空）

---

### 6. Portal Async Scheduler (`portal_async_scheduler`)

**功能定位**: 异步任务调度器，处理定时任务

**状态**: 待完善（README 为空）

---

## 📦 共享包详解

### Core Base (`core-base`)

**职责**: 提供最基础的通用组件

**依赖**:

- `pydantic` >= 2.12.5 - 数据验证
- `pydantic-settings` >= 2.12.0 - 配置管理
- `ruamel-yaml` >= 0.19.1 - YAML 解析
- `structlog` >= 25.5.0 - 结构化日志
- `concurrent-log-handler` >= 0.9.28 - 并发日志处理
- `uuid6` >= 2025.0.1 - UUID 生成

**核心功能**:

- `SettingsFactory` - 配置工厂类
- `get_logger()` - 日志获取函数

---

### Core Web (`core-web`)

**职责**: Web 应用核心组件

**依赖**:

- `fastapi` >= 0.135.0
- `core-base`
- `structlog`

**核心功能**:

- `AppFactory.create_app()` - FastAPI 应用工厂方法

---

### Core MQ (`core-mq`)

**职责**: 消息队列核心客户端

**依赖**:

- `aio-pika` >= 9.6.1 - 异步 AMQP 客户端
- `core-base`

---

### Core Redis (`core-redis`)

**职责**: Redis 客户端封装

**依赖**:

- `redis` >= 7.2.1
- `core-base`

**核心功能**:

- `RedisClientManager.initialize()` - 初始化连接池
- `RedisClientManager.close()` - 关闭连接

---

### Shared Domain (`shared-domain`)

**职责**: 领域层共享代码（数据库模型、ORM）

**依赖**:

- `sqlalchemy` >= 2.0.47 - ORM 框架
- `aiomysql` >= 0.3.2 - 异步 MySQL 驱动
- `core-base`

**核心组件**:

- `DatabaseManager` - 数据库连接管理器
- `MySQLSettings` - MySQL 配置模型
- ORM 模型文件（通过 sqlacodegen 生成）

**ORM 模型生成命令**:
在 `packages/shared_domain/` 目录下执行以下命令

```bash 
# 密码中的特殊字符需要进行 URL 编码
sqlacodegen mysql+pymysql://infound-stg:%263%24BSW%29mGxE%28Zk@db-zaxoqvvl.stg.infound.ai:8801/infound.stg --outfile src/shared_domain/models/infound.py
```

---

### Shared Application Services (`shared-application-services`)

**职责**: 应用服务层共享逻辑

**依赖**:

- `core-base`
- `shared-domain`

**核心基类**:

- `BaseDTO` - 数据传输对象基类（基于 Pydantic）

---

### Shared Infrastructure (`shared-infrastructure`)

**职责**: 基础设施层共享代码

**依赖**:

- `pydantic` >= 2.12.5
- `pydantic-settings` >= 2.12.0
- `core-base`

**核心功能**:

- 认证配置 (`IFAuthSettings`)
- 各类基础设施适配器

---

## 🛠️ 开发环境搭建

### 1. 安装 Python 3.13

```
# Windows 用户可通过 Microsoft Store 或官网下载安装
https://www.python.org/downloads/
```

### 2. 安装 UV 包管理器

```bash
# Windows (PowerShell)
powershell -c "irm paxton.ai/uv | iex"
```

```bash
# macOS/Linux
curl -LsSf https://astral.sh/uv/install.sh | sh
```

### 3. 同步项目依赖

```bash
# 在项目根目录执行
uv sync
```

### 4. 本地启动服务

#### 方式一：IDE 运行配置直接启动

#### 方式二：直接运行 FastAPI

```bash
# 启动达人服务
cd apps/portal_creator_open_api 
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8000
```

```bash
# 启动内部服务
cd apps/portal_inner_open_api 
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8001
```

```bash
#启动运营服务
cd apps/portal_operation_open_api 
uv run uvicorn main:app --reload --host 0.0.0.0 --port 8002
```

### 5. 配置多环境

每个服务都有独立的配置文件：

```yaml
apps/portal_creator_open_api/configs/
├── base.yaml # 基础配置（所有环境共用） 
├── dev.yaml # 开发环境配置 
├── stg.yaml # 预发布环境配置 
└── pro.yaml # 生产环境配置
```

**配置加载优先级**: `dev.yaml` | `stg.yaml` | `pro.yaml` > `base.yaml`

---

## 🔧 常用命令

### UV 命令

```bash
# 根目录下安装/同步环境
uv sync --all-packages
# 添加类库模块
uv init --lib packages/infrastructure
# 添加应用模块
uv init --app apps/portal_creator_open_api
# 添加本地依赖
cd apps/portal_creator_open_api uv add shared_infrastructure --workspace
# 添加第三方依赖
cd packages/shared_infrastructure uv add pydantic
```
