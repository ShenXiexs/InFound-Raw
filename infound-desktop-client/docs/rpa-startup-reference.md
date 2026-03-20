# XunDa RPA 启动总表

## 1. 目的

这份文档只记录 `apps/frontend.rpa.simulation` 当前唯一有效的机器人启动模型：

1. 先启动一个常驻 Playwright 会话
2. 会话启动后保持待命，不自动执行机器人
3. 后续再单独投送建联、样品管理、聊天机器人、达人详情任务

参考文档：

- [rpa-dispatch-reference.md](./rpa-dispatch-reference.md)
- [rpa-development-guide.md](./rpa-development-guide.md)
- [rpa-outreach-implementation.md](./rpa-outreach-implementation.md)
- [rpa-sample-management-implementation.md](./rpa-sample-management-implementation.md)
- [rpa-chatbot-implementation.md](./rpa-chatbot-implementation.md)
- [rpa-creator-detail-implementation.md](./rpa-creator-detail-implementation.md)
- [rpa-playwright-simulation-plan.md](./rpa-playwright-simulation-plan.md)
- [../apps/frontend.rpa.simulation/rpa-playwright-simulation-plan.md](../apps/frontend.rpa.simulation/rpa-playwright-simulation-plan.md)

### 快速总览

这份文档里所有可用启动入口，按场景汇总如下：

| 场景                 | 入口类型   | 指令或入口                                                                                      | 说明                                      |
| -------------------- | ---------- | ----------------------------------------------------------------------------------------------- | ----------------------------------------- |
| 启动应用             | 终端       | `cd apps/frontend.rpa.simulation && npx electron-vite dev --mode dev`                         | 启动 `frontend.rpa.simulation` 开发进程 |
| 登录态准备           | 界面       | `登录店铺`                                                                                    | 只准备登录态，不启动机器人                |
| 登录态准备           | 终端       | `login`                                                                                       | 只准备登录态，不启动机器人                |
| 启动 Playwright 会话 | 界面       | `启动RPA模拟`                                                                                 | 启动会话并待命                            |
| 启动 Playwright 会话 | IPC        | `RPA_EXECUTE_SIMULATION`                                                                      | 启动会话并待命                            |
| 启动 Playwright 会话 | 终端       | `start-simulation` / `start-simulation-headless` / `start-simulation-json <payload.json>` | 启动会话并待命                            |
| 样品管理任务         | IPC / 终端 | `RPA_SAMPLE_MANAGEMENT` / `sample-management ...`                                           | 复用已启动会话执行                        |
| 建联任务             | IPC / 终端 | `RPA_SELLER_OUT_REACH` / `outreach ...`                                                     | 复用已启动会话执行                        |
| 聊天任务             | IPC / 终端 | `RPA_SELLER_CHATBOT` / `chatbot ...`                                                        | 复用已启动会话执行                        |
| 达人详情任务         | IPC / 终端 | `RPA_SELLER_CREATOR_DETAIL` / `creator-detail ...`                                          | 复用已启动会话执行                        |
| 关闭会话             | 终端       | `stop-simulation`                                                                             | 关闭当前 Playwright 会话                  |
| 终端帮助             | 终端       | `help` / `exit` / `quit`                                                                  | 查看命令或退出终端模式                    |

## 2. 当前是否已实现

当前 `frontend.rpa.simulation` 中的 4 个机器人已经接到 Playwright 会话链路：

1. `RPA_EXECUTE_SIMULATION` 只负责启动 Playwright 会话
2. `RPA_SELLER_OUT_REACH` 只负责向已启动会话投送建联任务
3. `RPA_SAMPLE_MANAGEMENT` 只负责向已启动会话投送样品管理任务
4. `RPA_SELLER_CHATBOT` 只负责向已启动会话投送聊天任务
5. `RPA_SELLER_CREATOR_DETAIL` 只负责向已启动会话投送达人详情任务

旧 Electron 机器人执行路径已从 `frontend.rpa.simulation` 主链移除；当前保留 Electron 的只有 `登录店铺` 用于登录态准备。

## 3. 启动应用

```bash
cd apps/frontend.rpa.simulation
npx electron-vite dev --mode dev
```

如果本机同时有多个仓库副本，先确认当前目录是目标副本：

```bash
pwd -P
```

类型检查：

```bash
cd apps/frontend.rpa.simulation
npm run typecheck
```

## 4. 启动前置

当前 Playwright 会话默认会尝试使用：

```text
data/playwright/storage-state.json
```

说明：

1. 当前不自动桥接 Electron 登录态到 Playwright
2. `登录店铺` 不会启动机器人
3. `启动RPA模拟` 只会启动 Playwright 浏览器并待命
4. 如果 `storage-state.json` 存在，会直接带登录态进入 affiliate 首页
5. 如果 `storage-state.json` 不存在，不再报错；会直接打开登录页面等待手动操作
6. 如果请求无头启动但又找不到 `storage-state.json`，会自动切回有头模式

## 5. 如何启动 Playwright 会话

### 5.1 界面按钮

在 `frontend.rpa.simulation` 中点击：

- `启动RPA模拟`

当前行为：

1. 启动一个 Playwright Chromium 会话
2. 默认 `headless = false`，也就是默认有头
3. 如果存在 `storage-state.json`，会打开并停留在：
   - `https://affiliate.tiktok.com/platform/homepage?shop_region=<region>`
4. 如果不存在 `storage-state.json`，会打开：
   - `https://seller-mx.tiktok.com/`
     并等待手动登录
5. 会话保持待命，不自动执行任何机器人

### 5.2 IPC 启动

```ts
window.ipc.send(IPC_CHANNELS.RPA_EXECUTE_SIMULATION)
```

自定义启动 payload：

```ts
window.ipc.send(IPC_CHANNELS.RPA_EXECUTE_SIMULATION, {
  region: 'MX',
  headless: false,
  storageStatePath: 'data/playwright/storage-state.json'
})
```

当前 payload 结构：

```ts
{
  region?: string
  headless?: boolean
  storageStatePath?: string
}
```

默认值：

1. `region = 'MX'`
2. `headless = false`
3. `storageStatePath = 'data/playwright/storage-state.json'`

完整示例：

- `docs/examples/playwright-simulation-demo-payload.json`

### 5.3 终端启动

当前终端命令也遵守同一套模型：

```bash
start-simulation
start-simulation-headless
start-simulation-json docs/examples/playwright-simulation-demo-payload.json
```

## 6. 启动后如何投送任务

`<seller_login_email>`

`<seller_login_app_password>`

Playwright 会话启动完成后，再投送单独任务指令。

### 6.1 建联

```ts
window.ipc.send(IPC_CHANNELS.RPA_SELLER_OUT_REACH)
```

或带自定义 payload：

```ts
window.ipc.send(IPC_CHANNELS.RPA_SELLER_OUT_REACH, outreachPayload)
```

终端写法：

```bash
outreach
outreach-demo
outreach-json docs/examples/outreach-demo-payload.json
```

示例文件：

- `docs/examples/outreach-demo-payload.json`

### 6.2 样品管理

```ts
window.ipc.send(IPC_CHANNELS.RPA_SAMPLE_MANAGEMENT)
```

页面默认会先落在 `To review`；如果指定了其他 tab，运行时会从默认页点击切过去再抓。

指定单个 tab：

```ts
window.ipc.send(IPC_CHANNELS.RPA_SAMPLE_MANAGEMENT, {
  tab: 'completed'
})
```

指定多个 tab：

```ts
window.ipc.send(IPC_CHANNELS.RPA_SAMPLE_MANAGEMENT, {
  tabs: ['to_review', 'completed']
})
```

终端写法：

```bash
sample-management
sample-management completed
sample-management to_review,completed
sample-management-json docs/examples/sample-management-completed-payload.json
```

示例文件：

- `docs/examples/sample-management-completed-payload.json`

### 6.3 聊天机器人

```ts
window.ipc.send(IPC_CHANNELS.RPA_SELLER_CHATBOT, {
  creatorId: '<creator_id_demo>',
  message: 'halo'
})
```

终端写法：

```bash
chatbot <creator_id_demo>
chatbot-demo
chatbot-json docs/examples/chatbot-demo-payload.json
chatbot-json docs/examples/chatbot-halo-payload.json
```

示例文件：

- `docs/examples/chatbot-demo-payload.json`
- `docs/examples/chatbot-halo-payload.json`

### 6.4 达人详情

```ts
window.ipc.send(IPC_CHANNELS.RPA_SELLER_CREATOR_DETAIL, {
  creatorId: '<creator_id_demo>'
})
```

终端写法：

```bash
creator-detail <creator_id_demo>
creator-detail-demo
creator-detail-json docs/examples/creator-detail-demo-payload.json
```

示例文件：

- `docs/examples/creator-detail-demo-payload.json`

### 6.5 多个任务连续启动

当前没有“一条指令同时并发启动多个任务”的入口。

如果要在同一个 Playwright 会话里连续执行多个任务，正确方式是：

1. 先执行一次 `RPA_EXECUTE_SIMULATION`
2. 等会话启动完成并保持待命
3. 再按顺序逐个投送任务
4. 当前任务队列按串行执行，不要并发发送多个任务指令

IPC 示例：

```ts
window.ipc.send(IPC_CHANNELS.RPA_EXECUTE_SIMULATION)

window.ipc.send(IPC_CHANNELS.RPA_SAMPLE_MANAGEMENT, {
  tabs: ['to_review', 'completed']
})

window.ipc.send(IPC_CHANNELS.RPA_SELLER_OUT_REACH, outreachPayload)

window.ipc.send(IPC_CHANNELS.RPA_SELLER_CHATBOT, {
  creatorId: '<creator_id_demo>',
  message: 'halo'
})

window.ipc.send(IPC_CHANNELS.RPA_SELLER_CREATOR_DETAIL, {
  creatorId: '<creator_id_demo>'
})
```

终端顺序示例：

```bash
start-simulation
sample-management to_review,completed
outreach-demo
chatbot <creator_id_demo>
creator-detail <creator_id_demo>
```

说明：

1. 上面这些命令要复用同一个已启动的 Playwright 会话
2. 前一个任务未完成前，不要抢着发送下一个任务
3. 如果当前会话还停留在登录页，应先手动登录，再继续投送后续任务

## 7. 页面跳转是否和之前 Electron 一致

是。任务真正执行时，Playwright 会跳到和之前 Electron 机器人相同的业务页面：

1. 建联：`https://affiliate.tiktok.com/connection/creator?shop_region=<region>`
2. 样品管理：`https://affiliate.tiktok.com/product/sample-request?shop_region=<region>`
3. 聊天：`https://affiliate.tiktok.com/seller/im?creator_id=<creator_id>&shop_region=<region>`
4. 达人详情：`https://affiliate.tiktok.com/connection/creator/detail?cid=<creator_id>&shop_region=<region>`

区别只在于：

1. 现在这些页面跳转发生在已启动的 Playwright 会话里
2. 启动会话本身不会自动串行跑四个机器人

## 8. 当前边界

1. 当前所有机器人只允许走 Playwright 会话，不准走旧 Electron 机器人路径
2. 当前没有“启动会话后自动串行执行四个机器人”的入口
3. 当前如果未先启动 Playwright 会话就直接投送任务，会直接报错

## 9. 终端命令总表

当前终端命令入口与代码里 `printHelp()` 保持一致：

```text
login
start-simulation
start-simulation-headless
start-simulation-json <payload.json>
stop-simulation
sample-management [tab|tab1,tab2]
sample-management-json <payload.json>
outreach
outreach-demo
outreach-json <payload.json>
chatbot <creator_id>
chatbot-demo
chatbot-json <payload.json>
creator-detail <creator_id>
creator-detail-demo
creator-detail-json <payload.json>
help
exit
quit
```

推荐启动顺序：

```text
login
start-simulation
sample-management to_review,completed
outreach-demo
chatbot <creator_id_demo>
creator-detail <creator_id_demo>
```
