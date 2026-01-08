## INFound 数据采集服务

INFound 内部用于达人/商品信息丰富化的数据采集服务集合。仓库包含可复用的 RabbitMQ 消费与 Playwright 抓取基础设施（`common/`），以及两套样品爬虫实现：

- `apps/portal_tiktok_sample_crawler`：API 版本（通过 Partner API 获取样品列表/内容）
- `apps/portal_tiktok_sample_crawler_html`：网页抓取版本（Playwright，作为模板/兜底）

> **速览**
>
> 1. 配置由 `configs/base.yaml` 与 `apps/<service>/configs/*.yaml` 组合，`SERVICE_NAME` 环境变量决定加载哪个服务。
> 2. `main.py` 根据命令行参数启动指定的消费者，并通过 `common.mq` 接到 RabbitMQ。
> 3. 消费者从 RabbitMQ 读取 JSON 任务，将其交给服务层（示例中为 Playwright 爬虫）处理。

---

### 技术栈

- Python 3.13，依赖使用 Poetry 管理
- 异步组件：`asyncio`、`aio-pika`（RabbitMQ）、`Playwright`
- 数据访问：SQLAlchemy 2 + AsyncMy（未来可复用 `common.models`）
- 可观测性：`structlog`，并发安全的日志滚动

---

## 仓库结构

```
infound-data-collection/
├── apps/
│   ├── portal_tiktok_sample_crawler/         # API 版本
│       ├── crawler_consumer.py               # RabbitMQ 消费端入口
│       └── configs/{base,dev}.yaml           # 服务内配置
│   ├── portal_tiktok_sample_crawler_html/    # Playwright 网页抓取版本
│       ├── crawler_consumer.py               # RabbitMQ 消费端入口
│       ├── services/crawler_runner_service.py# Playwright 执行逻辑
│       └── configs/{base,dev}.yaml           # 服务内配置
│   └── sample_chatbot/                       # Chatbot 消费者（仅转发消息）
│       ├── crawler_consumer.py               # 消费端入口（dispatcher only）
│       ├── services/                         # 轮询/派发逻辑骨架
│       └── configs/{base,dev}.yaml           # 服务内配置
├── common/
│   ├── core/                                 # 配置 / 日志 / 数据库通用模块
│   ├── mq/                                   # RabbitMQ 连接 & 消费基类
│   └── models/all.py                         # SQLAlchemy 模型集合
├── configs/base.yaml                         # 全局默认配置
├── main.py                                   # CLI 启动入口
├── rabbitmq_connect_test.py                  # RabbitMQ 连通性测试脚本
├── pyproject.toml / poetry.lock
└── readme.md
```

---

## 配置模型

1. **环境变量**
   - `SERVICE_NAME`（必填）：决定加载 `apps/<SERVICE_NAME>/configs` 下的配置。
   - `ENV`（默认 `dev`）：决定使用 `apps/<SERVICE_NAME>/configs/<ENV>.yaml`。
   - 支持使用嵌套写法覆盖任意键，例如 `export RABBITMQ__PASSWORD=xxx`、`LOG_LEVEL=DEBUG`。
2. **配置文件**
   - `configs/base.yaml`：所有服务共享的默认值（系统名称、RabbitMQ 凭证、日志目录等）。
   - `apps/<service>/configs/base.yaml`：服务专属配置（交换机、队列、鉴权 token 等）。
   - `apps/<service>/configs/<env>.yaml`：按环境覆盖（示例给出 `dev.yaml`）。
3. **加载顺序**
   - `common.core.config.Settings` 会扁平化 YAML，并以 **全局 → 服务 base → 服务 env → 环境变量** 的顺序合并。
   - 如果未设置 `SERVICE_NAME`，`settings` 在导入时会直接抛出 `ValueError`。

---

## 本地运行指南

### 1. 前置依赖

- Python 3.13
- Poetry
- 已可访问的 RabbitMQ（脚本会连接实际服务器）
- Playwright 浏览器依赖（首次需执行 `playwright install`，Linux 可能还要安装系统依赖）

### 2. 安装依赖

```bash
cd /Users/samxie/Research/Infound_Influencer/InFound_Back/infound-data-collection
poetry env use python3.13          # 指定解释器
poetry lock                        # 使 lock 文件与 pyproject 对齐
poetry install --no-root           # 仅安装依赖，避免包布局报错
poetry run playwright install      # 下载浏览器
# 可选：进入虚拟环境交互
# poetry shell
```

### 3. 设置环境变量

```bash
export SERVICE_NAME=portal_tiktok_sample_crawler_html
export ENV=dev        # 若有 stg/pro 配置也可切换
export PLAYWRIGHT_HEADLESS=false     # 本地调试想看到页面可改为 false
```

### 4. 启动消费者

```bash
poetry run python main.py --consumer portal_tiktok_sample_crawler_html --env "$ENV"
```

可选参数：

- `--env`: 临时覆盖 `ENV`，如 `--env stg`
- `--all`: 预留用于同时启动 `settings.CONSUMERS` 中的全部消费者（目前只有一个）

使用 `Ctrl+C` 退出，`main.py` 会捕获 SIGINT/SIGTERM，调用 `consumer.stop()` 关闭 RabbitMQ 连接。

### 5. 后台运行（nohup 示例）

```bash
mkdir -p logs
nohup poetry run python main.py --consumer portal_tiktok_sample_crawler_html --env "$ENV" \
  > logs/portal_tiktok_sample_crawler_html.out 2>&1 &
tail -f logs/portal_tiktok_sample_crawler_html.out   # 实时查看输出
```

如需停止，查找 PID 后 `kill <pid>`。

---

## RabbitMQ 集成

- `common.mq.connection.RabbitMQConnection`
  - 声明 **direct** 交换机 + 专用死信交换机（`<exchange>.dlx`）与死信队列（`<queue>.dead`）。
  - 可配置的 QoS、重连间隔、最大重试次数。
  - 通过结构化日志输出连接/关闭状态。
- `common.mq.consumer_base.ConsumerBase`
  - 提供统一的消费循环与自动重连。
  - 解析 JSON 消息体并写入上下文日志，封装错误策略：
    - `ValueError`：`reject(requeue=False)`（格式错误，不重试）
    - `MessageProcessingError`：`reject(requeue=True)`（业务可重试）
    - 其他异常：`reject(requeue=False)`（防止死循环）
  - 使用 `async with message.process()` 确保手动 ACK/NACK。

示例消费者 `apps/portal_tiktok_sample_crawler_html/crawler_consumer.py` 继承该基类，从配置构造 RabbitMQ 连接，并将任务交给 `CrawlerRunnerService`。

---

## Collector → Inner API 写库链路

`portal_tiktok_sample_crawler_html` 现在不再直接写库，而是通过 `SampleIngestionClient` 将每批归一化结果 POST 到 backend inner API (`POST /samples/ingest`)，由 `SampleIngestionService` 负责聚合 content summary、去重 content 并落库。整体约定如下：

1. `apps/portal_tiktok_sample_crawler_html/services/sample_ingestion_client.py` 封装了基于 `httpx.AsyncClient` 的调用、鉴权和错误处理；当启用 `RABBITMQ.AT_MOST_ONCE=true` 时，任务不会重试，失败会记录日志并（尽力）投递到死信队列。
2. `CrawlerRunnerService._persist_results` 会把 `CrawlOptions`（`dataclasses.asdict`）和标准化 `rows` 打包，并附带 `source`（默认取 `settings.CONSUMER`）与当前 `operatorId`。
3. `apps/portal_tiktok_sample_crawler_html/configs/base.yaml` 中新增 `INNER_API` 配置，可通过环境变量覆盖：
   ```yaml
   INNER_API:
     BASE_URL: "<INNER_API_BASE_URL>"
     SAMPLE_PATH: "/samples/ingest"
     TIMEOUT: 30
   INNER_API_AUTH:
     REQUIRED_HEADER: "X-INFound-Inner-Service-Token"
     VALID_TOKENS: ["<INNER_API_TOKEN>"]
   ```
   将来上线环境只需设置 `INNER_API__BASE_URL` 和 `INNER_API_AUTH__TOKEN` 即可。
4. Collector 仍可按需导出 Excel/CSV；即便数据库临时不可达，只要 inner API 可访问即可完成任务，进一步降低了 Playwright 进程的权限需求。

### 请求/响应协定

- **URL**：`${INNER_API.BASE_URL}${INNER_API.SAMPLE_PATH}`
- **Headers**：
  - `Content-Type: application/json`
  - `${INNER_API_AUTH.REQUIRED_HEADER}: <token>`
- **Body**：
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
    "rows": [{ "...": "Playwright 整理后的字段" }]
  }
  ```
- **成功响应**：`{"code": 200, "msg": "success", "data": {"inserted": 40, "products": 9}}`
- **失败响应**：inner API 会返回 `code!=200` 或 HTTP 4xx/5xx，客户端会写日志并抛出 `MessageProcessingError`。

---

## Sample 系列专题

目前队列里只支持「Sample」系列的爬虫任务，因此每条消息都需要显式声明 `function: "sample"`（命令行脚本已默认带上）。后续增加新的功能链路时，可以在 `function` 上做分流，互不影响。

### Tab 对应关系

| MQ `tab` 值 | 页面标题             | URL 参数                |
| ------------- | -------------------- | ----------------------- |
| `review`    | To review            | `tab=to_review`       |
| `ready`     | Ready to ship        | `tab=ready_to_ship`   |
| `shipped`   | Shipped              | `tab=shipped`         |
| `pending`   | Content pending      | `tab=content_pending` |
| `completed` | Completed            | `tab=completed`       |
| `canceled`  | Canceled             | `tab=cancel`          |
| `all`       | 顺序遍历上述六个标签 | *依次跳转*            |

> `tab=all` 在页面上依次切换到 To review → Ready to ship → Shipped → Content pending → Completed → Canceled，方便一次性导出/写库全部状态。

---

## Playwright 爬虫服务

`apps/portal_tiktok_sample_crawler_html/services/crawler_runner_service.py` 现在完整复刻了历史 `sample_all.py` + `sample_process.py` 的功能，核心特性如下：

- **账号/区域管理**：支持通过配置文件或 MQ 消息选择账号、禁用账号、切换区域，内置 Gmail 验证码登录流程。
- **自动监控与抓取**：登录后常驻主页，监听 RabbitMQ 消息并按 tab（All/To review/Ready...）轮询，每条消息仅处理一个活动 ID。
- **精准筛选**：收到 `campaignId` 时自动在搜索框输入 Campaign ID，再分页抓取；`scanAllPages=true` 时会遍历整个 tab。
- **多 Action 处理**：除基础行解析外，实现了 View content 抽屉解析（视频/直播 Tab、多重重试）、View logistics 快照（基础信息+时间线+原始文本）以及 Approve 按钮可用性记录。
- **数据标准化与持久化**：按 `sample_process.py` 的标准对字段进行格式化、聚合 content_summary（含去重及 logistics 插桩），并实时更新 `samples`、`sample_crawl_logs`、`sample_contents`、`sample_content_crawl_logs`。
- **可选导出**：当 `exportExcel=true` 时会将规范化后的所有行同步导出为 `data/manage_sample/samples_<region>_<campaign>_<tabs>_<ts>.{xlsx,csv}`，方便人工校验与回溯。

### MQ 消息字段（推荐小驼峰）

| 字段                    | 类型                | 说明                                                                            |
| ----------------------- | ------------------- | ------------------------------------------------------------------------------- |
| `function`            | `str`             | 任务类型标识，当前仅支持 `sample`（并据此选择 Sample 系列逻辑）               |
| `campaignId`          | `str`             | 可选，指定 Campaign ID，默认遍历全部                                            |
| `accountName`         | `str`             | 可选，覆盖配置文件中的账号                                                      |
| `region`              | `str`             | 可选，默认 `settings.SAMPLE_DEFAULT_REGION`                                   |
| `tab` / `tabs`      | `str / list[str]` | 需要扫描的 tab（`all`/`review`/`ready`/...），支持传入数组                |
| `expandViewContent`   | `bool`            | 是否展开 View content 抽屉并解析视频/直播数据                                   |
| `viewLogistics`       | `bool`            | 是否点击 View logistics 并保存物流快照                                          |
| `scanAllPages`        | `bool`            | `true` 时分页遍历整个 tab；若缺省且提供 `campaignId`，默认只抓取首个匹配行 |
| `maxPages`            | `int`             | 最大翻页数，防止无限循环                                                        |
| `exportExcel`         | `bool`            | 是否在写库前额外导出 Excel/CSV                                                  |

所有字段均支持在 `configs/*.yaml` 中设置默认值。

### MQ 消息示例

- **最常用（单 Campaign + Completed 标签）**：

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

- **按多个 Campaign ID 顺序抓取（逐个搜索、每次等待加载 5~8 秒，抓完清空再下一个）**：

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

> 行为：每个 campaign 会重新点击目标 tab → 填入搜索框 → 回车/点放大镜并等待约 5 秒 → 抓取 → 清空搜索框再处理下一个。

- **全量遍历当前 tab（不指定活动）**：

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

> 说明：`tab=all` 会顺序遍历 To review / Ready to ship / Shipped / Content pending / Completed / Canceled 六个标签。只有提供 `campaignId` 时才会执行搜索过滤，否则按各标签的完整列表抓取。

- **指定活动 ID，抓取搜索结果的所有分页**：

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

将 JSON 发送到交换机 `crawler.direct`（按 tab 拆分投递；由 `portal_tiktok_sample_crawler` 单进程同时消费）：

- Completed 队列：routing key `crawler.tiktok.sample.completed.key` → 队列 `crawler.tiktok.sample.completed.queue`
- Other 队列：routing key `crawler.tiktok.sample.other.key` → 队列 `crawler.tiktok.sample.other.queue`

### 抓取与落库流程

1. **登录 & 主页监控**：启动 Playwright、完成 Gmail 验证码登录，并记录 tab 数量基线。
2. **任务执行**：对每个 tab -> 清空或输入 Campaign ID -> 分页调用 `_crawl_current_page`。每行除了基础字段，还会记录按钮状态、Creator 详情。
3. **Action 扩展**：
   - `View content`: 逐个 Tab（Video/Live）提取推广指标，内置重试/抽屉关闭。
   - `View logistics`: 抽取描述信息、表格、时间线与原始文本，存入 `content_summary`（`type="logistics"`）并在导出文件中以 JSON 形式保留。
4. **标准化**：数字/百分比/时间字段全部转换为整数或 Decimal，`content_summary` 依据 `platform_product_id` 去重聚合，保证所有 promotion/logistics 条目唯一。
5. **写库 & 导出**：将标准化结果分别 upsert 到 4 张样品相关表，并根据选项导出 Excel/CSV。

Playwright 相关依赖需通过 `poetry run playwright install` 安装，推荐在消费者启动阶段完成一次 `initialize()` 以复用浏览器实例。

### 功能清单（已对齐旧版 sample_all.py / sample_process.py）

- **账号策略**：支持配置文件的多账号、禁用位、区域优先匹配；MQ 可指定 `accountName`/`region`，未命中时回退默认账号。
- **登录与验证码**：Gmail App 密码拉取验证码；失败自动重试 3 次。
- **首页监控**：登录后记录 tab 计数，任务前比对增量（新消息提醒）。
- **消息协议**：支持 tab 数组、区域/账号/是否展开 View content、是否抓物流、是否全量翻页、最大页数、是否导出 Excel/CSV。
- **搜索与分页**：若 `campaignId` 且未开启全量，先填入搜索框并仅抓取匹配行；全量则清空搜索并逐页抓取，分页按钮含重试。
- **行解析**：商品/活动 ID、SKU、库存、可用样品、状态、剩余时间、post_rate、is_showcase、creator 信息等全部保留。
- **Action 解析**：识别 View content / View logistics / Approve，记录按钮是否禁用；可按开关执行物流抽屉抓取。
- **View content 抽屉**：多次重试、按 Video/Live tab 提取推广指标，支持特殊布局与兜底空值。
- **View logistics 抽屉**：解析描述列表、表格、时间线事件与原始文本，并写入 content_summary 的 `type="logistics"` 条目。
- **字段规范化**：沿用 `sample_process.py` 的转换规则，含缩写数字（k/m）、百分比、时间残留、布尔统一等，避免科学计数。
- **content_summary 去重**：同一商品按 JSON 去重 promotion/logistics 条目，无数据时写入空条目保证 JSON 列有效。
- **写库**：实时 upsert `samples`、`sample_crawl_logs`、`sample_contents`、`sample_content_crawl_logs`。时间字段用 UTC，操作人取 `settings.SAMPLE_DEFAULT_OPERATOR_ID`。
- **导出**：若 `exportExcel=true`，将标准化后的所有行导出到 `data/manage_sample/samples_<region>_<campaign>_<tabs>_<ts>.xlsx/csv`，并对列表/JSON 字段序列化方便审阅。

## 样品 Chatbot（MX 区域）

- 启动方式：设置 `SERVICE_NAME=sample_chatbot`、`ENV=<env>` 后执行 `poetry run python main.py --consumer sample_chatbot`。
- 职责拆分：
  - Inner API：入库后写入 `sample_chatbot_schedules`（状态变更/提醒规则），并由后台任务批量投递 MQ。
  - `sample_chatbot`：只消费 MQ 并通过 Playwright 发送聊天消息（不再轮询 DB 生产任务）。
- RabbitMQ（topic）约定：
  - Exchange：`chatbot.topic`
  - Queue：`chatbot.sample.queue.topic`（DLQ：`chatbot.sample.queue.topic.dead`，DLX：`chatbot.topic.dlx`）
  - 发布 routing key：`chatbot.sample.batch`（队列绑定：`chatbot.sample.*`）
- 消息格式（小驼峰；`messages` 必填，可直接发送数组或使用 `tasks` 包装）：
  - 任务数组（推荐）：
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
  - 批量包装（兼容）：
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
  - 可选字段：`accountName`（指定发送账号）、`from`/`operatorId`（发送者 ID）、`sampleId`、`platformProductId`、`platformProductName`、`platformCampaignName`、`platformCreatorUsername`、`creatorWhatsapp`。
- 消息生成：Inner API/运营中台负责生成并下发消息内容；`sample_chatbot` 只按 `messages` 转发，不管理模板/场景。
- 失败与重发：
  - 单条 task 发送失败会投递到 DLQ `chatbot.sample.queue.topic.dead`（不会吞掉整批）。
  - 可用 `poetry run python tools/requeue_chatbot_dlq.py --consumer sample_chatbot --env <env>` 将 DLQ 消息重新投递回主 exchange。

## 建联任务（Creator Outreach）

### 运行链路（爬虫 → Inner API → MQ/发送）

1. `portal_tiktok_creator_crawler` 通过 Playwright 登录、筛选、滚动加载达人列表并抓取详情/联系方式。
2. 每个达人抓取结果会发送到 Inner API `/creators/ingest` 进行入库（`creators` + `creator_crawl_logs`）。
3. 任务进度/状态同步到 Inner API `/outreach_tasks/ingest`（建联任务表）。
4. 若满足发送条件，则向 Inner API `/chatbot/messages` 发送消息任务；Inner API 再转发到 RabbitMQ，由 `sample_chatbot` 消费并通过 Playwright 发送。

### Inner API 调用

- **创建/更新建联任务**：`POST /outreach_tasks/ingest`
  - Body（小驼峰；`task` 可扩展字段）：
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
  - `operatorId`：账号/操作人 UUID（用于审计字段）。

- **达人数据入库**：`POST /creators/ingest`
  - Body：`source`/`operatorId`/`options`/`rows`；`rows` 里包含 `creator_id`、`creator_name`、`categories`、`followers`、`gmv`、`contact`、`connect/reply/send` 等完整字段。

- **发送消息任务**：`POST /chatbot/messages`
  - 与样品 Chatbot 的 payload 格式一致，Inner API 会转发到 RabbitMQ。

### RabbitMQ 约定

- 交换机/队列与 `sample_chatbot` 共用：
  - Exchange：`chatbot.topic`
  - Queue：`chatbot.sample.queue.topic`（DLQ：`chatbot.sample.queue.topic.dead`，DLX：`chatbot.topic.dlx`）
  - Routing key：`chatbot.sample.batch`（队列绑定：`chatbot.sample.*`）

### 字段规范化与入库映射（与 sample_process.py 对齐）

- **ID/标识**：`platform_product_id` 必填；`platform_campaign_id` 归一化（去前后空格、纯数字去前导 0）；空值行直接丢弃。
- **数值**：`available_sample_count`、`stock`、`promotion_view/like/comment/order` → 整数；`post_rate`、`promotion_order_total_amount` → Decimal。
- **时间/字符串**：`request_time_remaining` 归一化为 “X days/hours”；`extracted_time` 统一 UTC 文本。
- **布尔**：`is_showcase`、`is_uncooperative`、`is_unapprovable` 填充 0/False。
- **creator 信息**：`platform_creator_display_name`/`platform_creator_username`/`platform_creator_id`/`creator_url` 全部落库；用户名自动去 @。
- **content_summary**：按 `platform_product_id` 聚合，包含 Video/Live promotion 指标及物流事件，避免重复记录；空则写入一条空 summary。
- **日志表**：`SampleCrawlLogs` 按天记录全量字段；`SampleContentCrawlLogs` 保存每条内容（Video/Live）明细。
- **导出列顺序**：保持旧版 Excel 字段顺序，附带 `actions`、`action_details`、`logistics_snapshot` 的 JSON。

### 实际操作提示

1. **准备配置**：在 `apps/portal_tiktok_sample_crawler_html/configs/*.yaml` 配置账号、区域、默认 tab 与开关（`SAMPLE_EXPAND_VIEW_CONTENT`、`SAMPLE_VIEW_LOGISTICS_ENABLED`、`SAMPLE_ENABLE_EXCEL_EXPORT`）。
2. **运行**：设置 `SERVICE_NAME=portal_tiktok_sample_crawler_html`，启动消费者；向队列投递消息时，可附 `{"campaignId": "...", "viewLogistics": true, "exportExcel": true}` 验证。
3. **验证**：关注日志中的 tab 计数 diff、登录成功提示；检查导出目录 `data/manage_sample/` 与数据库 `samples`/`sample_contents` 是否有对应记录。
4. **故障排查**：如果登录/抽屉偶发超时，重试已内置；若页面结构再变化，可更新 `SAMPLE_SEARCH_INPUT_SELECTOR` 或 selector 片段后重跑。

### 样品爬虫账号配置

- 账号配置文件：`configs/accounts.json`（由 `SAMPLE_ACCOUNT_CONFIG_PATH` 指定，已创建）。MQ 消息可用 `accountName`、`region` 强制选择账号，否则按「区域匹配 → 启用优先」顺序自动挑选。禁用账号 `enabled=false` 时不会被使用。
- 当前内置账号：
  > 所有账号邮箱/密码都已替换为占位符，讲演/演示版本不会暴露真实凭据。
  - `MX1`（region MX）：`mx1@example.com` / Gmail App 密码 `<GMAIL_APP_PASSWORD>`
  - `MX2`（region MX）：`mx2@example.com` / Gmail App 密码 `<GMAIL_APP_PASSWORD>`
  - `MX3`（region MX）：`mx3@example.com` / Gmail App 密码 `<GMAIL_APP_PASSWORD>`
  - `MX4`（region MX，已禁用，需要 luna 启动程式码）：`mx4@example.com`（禁用账号，密码留空）
  - `FR1`（region FR）：`fr1@example.com` / Gmail App 密码 `<GMAIL_APP_PASSWORD>`
- 单账号兜底：如果未找到 `accounts.json`，会回退到 `apps/portal_tiktok_sample_crawler_html/configs/base.yaml` 中的 `SAMPLE_LOGIN_EMAIL/SAMPLE_GMAIL_USERNAME/...`。
- 建议：如需调整优先级，直接在 `accounts.json` 重排顺序或设置 `enabled=false`；跨区域任务请在消息里显式传 `region` 以选到对应账号。

---

## 数据访问工具

- `common.core.database`
  - 基于 `settings.SQLALCHEMY_DATABASE_URL` 创建异步 SQLAlchemy 引擎。
  - 暴露 `get_db()` 上下文管理器，方便在服务/DAO 中注入会话。
- `common.models/all.py`
  - 使用 `sqlacodegen` 生成的 INFound 业务表模型，覆盖活动、达人、样品等数据结构。
  - 未来可按需导入（如 `from common.models.all import Creators`）实现持久化逻辑。

目前示例消费者尚未落库，但这些模块已就绪。

---

## 日志与可观测性

- `common.core.logger`
  - 基于 `structlog`，同时输出控制台（本地时间、易读）与文件（JSON，支持并发安全滚动）。
  - 日志文件位于 `logs/<APP_NAME>.log`，可通过 `LOG_DIR`、`LOG_FILE_MAX_SIZE`、`LOG_FILE_BACKUP_COUNT` 等配置调整。
  - 自动合并上下文（消费者名称、请求 ID 等），便于排查问题。
- `common.core.exceptions`
  - 统一定义 `RabbitMQConnectionError`、`MessageProcessingError`、`PlaywrightError` 等异常，方便在业务中区分处理策略。

---

## 工具与排障

- `rabbitmq_connect_test.py`

  ```bash
  poetry run python rabbitmq_connect_test.py
  ```

  独立使用 `aio-pika.connect_robust` 验证连通性，可快速定位防火墙/凭证问题。若需使用不同凭证，可修改 `configs/base.yaml` 或通过环境变量覆盖。

---

## 新增消费者的步骤

1. 创建目录结构：
   ```
   apps/<new_consumer>/
     ├── crawler_consumer.py
     ├── services/...
     └── configs/{base,dev,stg,pro}.yaml
   ```
2. 在 `configs/base.yaml` 的 `CONSUMERS` 中加入新服务名称。
3. 运行前设置 `SERVICE_NAME=<new_consumer>`。
4. 在 `process_message_body` 中校验消息、调用业务逻辑，并在可重试的场景抛出 `MessageProcessingError`。

通过该结构可以最大程度复用 RabbitMQ、日志与配置逻辑，只需专注于具体业务。

---

## 开发工作流

- 代码格式化：`poetry run black .`
- Lint：`poetry run flake8`
- 新增依赖：`poetry add <package>`；锁文件：`poetry lock --no-update`
- 测试：当前尚未内置测试目录，可根据需要新增 `tests/`

提交代码时请保持配置与环境解耦，并在 README 中补充新消费者说明。业务代码优先使用 `common.core.exceptions` 中的异常类型，保持处理一致性。

---

## 常见问题（FAQ）

- **为什么导入 `common.core.config` 会立即报错？**因为配置在模块导入时立即实例化，所有模块共享一个 `settings`。未设置 `SERVICE_NAME` 会导致应用在启动前就抛出异常。
- **如何为不同环境配置 RabbitMQ？**在 `apps/<service>/configs/` 中新增 `stg.yaml`、`pro.yaml` 等文件，覆写 `RABBITMQ: {HOST: "...", ROUTING_KEY: "...", ...}`。仍可使用环境变量覆盖敏感字段。
- **生产环境日志写在哪里？**
  默认写入仓库内的 `logs/` 目录，可挂载或改写 `LOG_DIR`。容器化部署时建议将日志目录映射到宿主机或日志系统。
