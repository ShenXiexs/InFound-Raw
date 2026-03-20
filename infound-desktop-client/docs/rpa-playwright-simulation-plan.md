# RPA Playwright Simulation Plan

## Goal

`frontend.rpa.simulation` 当前采用单一模型：

1. 先启动 Playwright 会话
2. 会话启动后保持待命
3. 再通过单独任务指令驱动四个机器人

## Current Entry Model

### Session startup

- UI button: `启动RPA模拟`
- IPC: `RPA_EXECUTE_SIMULATION`
- CLI:
  - `start-simulation`
  - `start-simulation-headless`
  - `start-simulation-json <payload.json>`

### Task dispatch

- Outreach: `RPA_SELLER_OUT_REACH`
- Sample Management: `RPA_SAMPLE_MANAGEMENT`
- Chatbot: `RPA_SELLER_CHATBOT`
- Creator Detail: `RPA_SELLER_CREATOR_DETAIL`

## Constraints

1. 当前所有机器人只允许跑在 Playwright 会话里
2. 不允许再走旧 Electron 机器人链路
3. `登录店铺` 仍可存在，但只负责登录态准备
4. 当前不自动桥接 Electron 登录态到 Playwright storage state
5. 如果没有 storage state，会直接打开登录页等待手动登录

## Session Behavior

1. 默认有头：`headless = false`
2. 启动后会打开 affiliate 首页待命：
   - `https://affiliate.tiktok.com/platform/homepage?shop_region=<region>`
3. 启动会话不会自动串行跑 4 个机器人
4. 后续投送的任务会复用同一个 Playwright browser/context/page
5. 任务按顺序串行执行

## Task Navigation

任务执行时，跳转页与之前 Electron 机器人保持一致：

1. Outreach:
   - `https://affiliate.tiktok.com/connection/creator?shop_region=<region>`
2. Sample Management:
   - `https://affiliate.tiktok.com/product/sample-request?shop_region=<region>`
3. Chatbot:
   - `https://affiliate.tiktok.com/seller/im?creator_id=<creator_id>&shop_region=<region>`
4. Creator Detail:
   - `https://affiliate.tiktok.com/connection/creator/detail?cid=<creator_id>&shop_region=<region>`

## Storage State

Required file:

- `data/playwright/storage-state.json`

If the file does not exist, session startup opens the seller login page and waits for manual operation.
