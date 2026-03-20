# RPA 投送与启动参考

启动总表见：

- [rpa-startup-reference.md](./rpa-startup-reference.md)

## 1. 目的

这份文档只记录当前 Playwright 会话模型下的投送方式：

1. 如何启动会话
2. 会话启动后如何单独投送 4 个机器人任务

## 2. 强制约束

1. 当前所有机器人只允许跑在 `apps/frontend.rpa.simulation` 的 Playwright 会话中
2. 不允许再走旧 Electron 机器人执行路径
3. `RPA_EXECUTE_SIMULATION` 现在只负责启动会话，不负责自动执行任何机器人
4. 任务必须在会话启动成功后再单独投送

## 3. 启动 Playwright 会话

### 3.1 默认启动

```ts
window.ipc.send(IPC_CHANNELS.RPA_EXECUTE_SIMULATION)
```

默认效果：

1. `region = 'MX'`
2. `headless = false`
3. `storageStatePath = 'data/playwright/storage-state.json'`
4. 如果找到 `storage-state.json`，浏览器会停留在 affiliate 首页待命
5. 如果没找到 `storage-state.json`，浏览器会打开登录页等待手动登录

### 3.2 自定义启动

```ts
window.ipc.send(IPC_CHANNELS.RPA_EXECUTE_SIMULATION, {
  region: 'MX',
  headless: false,
  storageStatePath: 'data/playwright/storage-state.json'
})
```

完整示例文件：

- `docs/examples/playwright-simulation-demo-payload.json`

### 3.3 终端启动

```bash
start-simulation
start-simulation-headless
start-simulation-json docs/examples/playwright-simulation-demo-payload.json
```

## 4. 任务投送时机

只有在 Playwright 会话已经启动并保持待命之后，才可以发送下面这些任务指令：

1. `RPA_SELLER_OUT_REACH`
2. `RPA_SAMPLE_MANAGEMENT`
3. `RPA_SELLER_CHATBOT`
4. `RPA_SELLER_CREATOR_DETAIL`

如果会话未启动，任务会直接失败。
如果会话当前还停留在手动登录页，则应先完成登录，再投送任务。

## 5. 建联任务投送

### 5.1 默认投送

```ts
window.ipc.send(IPC_CHANNELS.RPA_SELLER_OUT_REACH)
```

这会使用建联 demo payload。

### 5.2 自定义投送

```ts
window.ipc.send(IPC_CHANNELS.RPA_SELLER_OUT_REACH, {
  creatorFilters: {
    productCategorySelections: ['Home Supplies']
  }
})
```

示例文件：

- `docs/examples/outreach-demo-payload.json`

## 6. 样品管理任务投送

```ts
window.ipc.send(IPC_CHANNELS.RPA_SAMPLE_MANAGEMENT)
```

页面默认会先落在 `To review`；如果指定了别的 tab，运行时会先点到目标 tab 再抓接口。

默认会抓：

1. `To review`
2. `Ready to ship`
3. `Shipped`
4. `In progress`
5. `Completed`

也可以指定某个 tab 或一组 tabs：

```ts
window.ipc.send(IPC_CHANNELS.RPA_SAMPLE_MANAGEMENT, {
  tab: 'completed'
})
```

```ts
window.ipc.send(IPC_CHANNELS.RPA_SAMPLE_MANAGEMENT, {
  tabs: ['to_review', 'completed']
})
```

示例文件：

- `docs/examples/sample-management-completed-payload.json`

终端写法：

```bash
sample-management
sample-management completed
sample-management to_review,completed
sample-management-json docs/examples/sample-management-completed-payload.json
```

## 7. 聊天任务投送

```ts
window.ipc.send(IPC_CHANNELS.RPA_SELLER_CHATBOT, {
  creatorId: '<creator_id_demo>',
  message: 'halo'
})
```

示例文件：

- `docs/examples/chatbot-demo-payload.json`
- `docs/examples/chatbot-halo-payload.json`

## 8. 达人详情任务投送

```ts
window.ipc.send(IPC_CHANNELS.RPA_SELLER_CREATOR_DETAIL, {
  creatorId: '<creator_id_demo>'
})
```

示例文件：

- `docs/examples/creator-detail-demo-payload.json`

## 9. 终端任务投送

当前终端命令也全部走同一条 Playwright 会话：

```bash
sample-management
sample-management completed
sample-management to_review,completed
sample-management-json docs/examples/sample-management-completed-payload.json
outreach
outreach-demo
outreach-json docs/examples/outreach-demo-payload.json
chatbot <creator_id_demo>
chatbot-demo
chatbot-json docs/examples/chatbot-demo-payload.json
creator-detail <creator_id_demo>
creator-detail-demo
creator-detail-json docs/examples/creator-detail-demo-payload.json
```

## 10. 任务执行时的页面跳转

任务执行时，Playwright 会跳转到这些页面：

1. 建联：`https://affiliate.tiktok.com/connection/creator?shop_region=<region>`
2. 样品管理：`https://affiliate.tiktok.com/product/sample-request?shop_region=<region>`
3. 聊天：`https://affiliate.tiktok.com/seller/im?creator_id=<creator_id>&shop_region=<region>`
4. 达人详情：`https://affiliate.tiktok.com/connection/creator/detail?cid=<creator_id>&shop_region=<region>`
