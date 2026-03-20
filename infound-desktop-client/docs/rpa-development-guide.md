# XunDa RPA 开发需求指南（Simulation First）

## 1. 文档目的

本指南用于固定 `apps/frontend.rpa.simulation` 的当前开发基线。

当前只接受这一套执行模型：

1. 启动一个常驻 Playwright 会话
2. 所有机器人任务都投送到这条 Playwright 会话
3. 不允许再保留旧 Electron 机器人执行链

目标机器人共 4 个：

1. 建联机器人
2. 样品管理机器人
3. 聊天机器人
4. 达人详情机器人

## 2. 当前开发边界

1. 代码改动先限定在 `apps/frontend.rpa.simulation`
2. 当前不要求下沉到 `packages/frontend.desktop.shared`
3. 旧 Electron 机器人逻辑不再作为当前实现的一部分
4. `登录店铺` 只负责登录态准备，不负责启动机器人
5. `RPA_EXECUTE_SIMULATION` 只负责启动 Playwright 会话，不负责自动跑任务

## 3. 当前系统结构

1. `src/main/modules/ipc/rpa-controller.ts`
   - 登录入口
   - Playwright 会话启动入口
   - 单独任务投送入口
2. `src/main/modules/rpa/task-dsl/*`
   - 当前通用 DSL
3. `src/main/modules/rpa/playwright-simulation/*`
   - `PlaywrightSimulationService`
   - `PlaywrightBrowserActionTarget`
   - `PlaywrightJsonResponseCaptureManager`
   - `PlaywrightSampleManagementCrawler`
4. 机器人专属模块
   - `outreach/support.ts`
   - `chatbot/support.ts`
   - `creator-detail/support.ts`
   - `sample-management/*`

## 4. 四个机器人现状

| 机器人 | 当前状态 | 当前入口 |
| --- | --- | --- |
| 建联机器人 | 已接到 Playwright 会话，投送后执行筛选/搜索/滚动采集 | `RPA_SELLER_OUT_REACH` |
| 样品管理机器人 | 已接到 Playwright 会话，默认执行 5 tab API 解析，也可指定 tab/tabs | `RPA_SAMPLE_MANAGEMENT` |
| 聊天机器人 | 已接到 Playwright 会话，投送后执行 IM 发送与校验 | `RPA_SELLER_CHATBOT` |
| 达人详情机器人 | 已接到 Playwright 会话，投送后执行详情提取与导出 | `RPA_SELLER_CREATOR_DETAIL` |

## 5. 启动与投送模型

### 5.1 启动会话

先启动应用：

```bash
cd apps/frontend.rpa.simulation
npx electron-vite dev --mode dev
```

然后保证存在：

```text
data/playwright/storage-state.json
```

再启动 Playwright 会话：

```ts
window.ipc.send(IPC_CHANNELS.RPA_EXECUTE_SIMULATION)
```

或：

```bash
start-simulation
```

当前会话默认：

1. `region = 'MX'`
2. `headless = false`
3. 如果存在 `storage-state.json`，打开 affiliate 首页待命
4. 如果不存在 `storage-state.json`，打开登录页等待手动登录

### 5.2 投送任务

会话启动后，再分别发送：

1. `RPA_SELLER_OUT_REACH`
2. `RPA_SAMPLE_MANAGEMENT`
3. `RPA_SELLER_CHATBOT`
4. `RPA_SELLER_CREATOR_DETAIL`

当前不再支持“启动会话后自动串行执行四个机器人”。

## 6. 当前执行页面

任务实际运行时，Playwright 会跳转到和之前 Electron 一致的业务页面：

1. 建联：`https://affiliate.tiktok.com/connection/creator?shop_region=<region>`
2. 样品管理：`https://affiliate.tiktok.com/product/sample-request?shop_region=<region>`
3. 聊天：`https://affiliate.tiktok.com/seller/im?creator_id=<creator_id>&shop_region=<region>`
4. 达人详情：`https://affiliate.tiktok.com/connection/creator/detail?cid=<creator_id>&shop_region=<region>`

## 7. 当前开发原则

1. `RPAController` 只保留入口编排，不直接承载旧 Electron 机器人实现
2. DSL 继续服务于通用浏览器动作，不新增 Electron 专属机器人逻辑
3. Playwright 会话应保持常驻、可复用、串行执行任务
4. 任务未启动会话时必须明确报错，不能偷偷退回 Electron 路径
5. 所有文档都要以 Playwright 会话模型为准

## 8. 当前验收标准

### 8.1 会话层

1. 可启动有头或无头 Playwright
2. 默认有头
3. 启动后停留待命，不自动跑机器人
4. 可以多次投送单独任务

### 8.2 任务层

1. 建联任务投送后可跳转建联页并执行
2. 样品管理任务投送后可跳转样品管理页并执行
3. 聊天任务投送后可跳转 IM 页并执行
4. 达人详情任务投送后可跳转详情页并执行
5. 所有任务都只跑在 Playwright 会话里
