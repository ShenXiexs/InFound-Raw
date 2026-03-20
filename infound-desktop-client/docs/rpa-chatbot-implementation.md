# XunDa RPA 聊天机器人实现说明

当前文档对应的执行入口是 `apps/frontend.rpa.simulation` 中的 Playwright 模拟链路：

- [../apps/frontend.rpa.simulation/rpa-playwright-simulation-plan.md](../apps/frontend.rpa.simulation/rpa-playwright-simulation-plan.md)

说明：

1. `登录店铺` 只负责准备登录态，不负责启动聊天机器人。
2. `启动RPA模拟` 只负责启动 Playwright 会话，不自动执行聊天机器人。
3. 聊天机器人当前通过单独任务指令 `RPA_SELLER_CHATBOT` 投送到已启动的 Playwright 会话。
4. Playwright 模拟会优先使用 `data/playwright/storage-state.json`；如果文件不存在，会打开登录页等待手动登录。

## 1. 本次实现范围

当前聊天机器人在 Playwright 模拟链路中的实现范围为：

1. 使用预先准备好的 Playwright `storageState` 打开浏览器上下文。
2. 读取模拟 payload 中的 `shop_region`，未传时默认使用 `MX`。
3. 跳转到：
   - `https://affiliate.tiktok.com/seller/im?creator_id=<creator_id>&shop_region=<region>`
4. 以聊天输入框 `textarea` 可见作为 IM 页加载完成信号。
5. 页面加载完成后读取：
   - 达人显示名
   - 当前聊天记录文本
6. 将指定消息填入聊天输入框。
7. 先校验输入字数不是 `0/2000`。
8. 先用原生点击方式点击 `Send` 按钮发送消息。
9. 按钮发送后，检查输入字数是否从非 0 变回 `0`。
10. 如果输入字数未归零，则认为本轮发送失败并重试，最多 3 次。
11. 最后再次读取完整聊天记录文本。
12. 将本次关键内容写入：
   - `data/chatbot/seller_chatbot_session_<timestamp>.md`

说明：

1. 当前如果没有单独传入聊天任务 payload，终端 demo 命令会使用 `createDemoSellerChatbotPayload()`。

## 2. 关键页面元素

当前实现使用以下 selector：

1. 就绪输入框 / 聊天输入框：
   - `textarea[data-e2e="798845f5-2eb9-0980"], textarea#imTextarea, #im_sdk_chat_input textarea, textarea[placeholder="Send a message"]`
2. 发送按钮：
   - `#im_sdk_chat_input > div.footer-zRiuSb > div > button`
3. 输入字数计数：
   - `div[data-e2e="6981c08f-68cc-5df6"] span[data-e2e="76868bb0-0a54-15ad"]`
   - 发送成功时预期从非 `0` 变回 `0`
4. 聊天记录容器：
   - `div[data-e2e="4c874cc7-9725-d612"], div.messageList-tkdtcN, div.chatd-scrollView`
5. 达人显示名：
   - `div[data-e2e="4e0becc3-a040-a9d2"], div.personInfo-qNFxKc .text-body-m-medium`

## 3. 任务执行链路

当前 Playwright 聊天机器人任务步骤如下：

1. `goto`
2. `waitForSelector(chat input visible)`
3. `waitForSelector(chat input)`
4. `readText(creator name)`
5. `readText(transcript before send)`
6. `fillSelector(chat input)`
7. `clickSelector(chat input)` 保证输入框聚焦
8. `readText(input count)`
9. `assertData(input count != 0)`
10. `clickSelector(send button, native=true)`
11. `waitForTextChange(input count -> input count after)`
12. `readText(input count after)`
13. 比较“输入字数是否归零”
14. `readText(transcript after send)`

说明：

1. 当前发送主路径是原生点击 `Send` 按钮。
2. 发送前会先校验输入字数不是 `0`，用于确认消息确实已经写入输入框。
3. 发送成功的主信号是输入字数从非 `0` 变回 `0`。
4. 聊天记录读取使用 `innerText` 保留换行，便于落地到 markdown。
5. 当前最多发送重试 3 次。

## 4. Playwright 模拟入口

1. 启动 `apps/frontend.rpa.simulation`。
2. 可选地准备 Playwright 登录态文件：
   - `data/playwright/storage-state.json`
3. 点击渲染层按钮：
   - `启动RPA模拟`
4. Playwright 会话启动后，再投送：
   - `RPA_SELLER_CHATBOT`
5. 当前聊天机器人会复用本文档记录的步骤链路。

## 5. 会话日志落盘

每次聊天任务完成后，会生成一份 markdown：

- `data/chatbot/seller_chatbot_session_<timestamp>.md`

内容包括：

1. `creator_id`
2. `creator_name`
3. `region`
4. `target_url`
5. 就绪输入框 selector
6. 输入框 selector
7. 发送按钮 selector
8. 输入字数 selector
9. 聊天记录 selector
10. 发送消息正文
11. 发送前聊天记录
12. 发送是否校验通过
13. 发送尝试次数
14. 发送后聊天记录
15. 发送后聊天记录是否变化

## 6. 默认消息

当前如果 payload 不传 `message`，会使用内置默认消息：

```text
hi
```

## 7. 当前限制

1. 当前一次只处理一个 `creator_id`。
2. 当前发送校验基于输入字数归零，没有再保留额外的消息内容级兜底分支。
3. 当前没有实现批量调度、去重发送、消息模板切换、产品卡片发送。
4. 当前只实现主进程 CLI / IPC 入口，没有单独做聊天机器人页面 UI 配置器。
