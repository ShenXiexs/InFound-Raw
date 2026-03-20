# XunDa RPA 样品管理爬取实现说明

当前文档对应的执行入口是 `apps/frontend.rpa.simulation` 中的 Playwright 模拟链路：

- [../apps/frontend.rpa.simulation/rpa-playwright-simulation-plan.md](../apps/frontend.rpa.simulation/rpa-playwright-simulation-plan.md)

说明：

1. `登录店铺` 只负责准备登录态，不负责启动样品管理机器人。
2. `启动RPA模拟` 只负责启动 Playwright 会话，不自动执行样品管理机器人。
3. 样品管理机器人当前通过单独任务指令 `RPA_SAMPLE_MANAGEMENT` 投送到已启动的 Playwright 会话。
4. Playwright 模拟会优先使用 `data/playwright/storage-state.json`；如果文件不存在，会打开登录页等待手动登录。

## 1. 当前实现范围

当前样品管理在 Playwright 模拟链路中已经切到 API 响应解析，不再以旧的 DOM 逐列读取作为主方法。

当前默认抓取 5 个 tab：

1. `To review`
2. `Ready to ship`
3. `Shipped`
4. `In progress`
5. `Completed`

统一使用：

1. 页面 tab 切换
2. 请求接口：`GET /api/v1/affiliate/sample/group/list`
3. 分页方式：点击分页 `Next`
4. `Completed` 额外补抓：`GET /api/v1/affiliate/sample/performance`
5. 导出方式：Excel

## 2. Playwright 模拟入口

1. 启动 `apps/frontend.rpa.simulation`。
2. 可选地准备 Playwright 登录态文件：
   - `data/playwright/storage-state.json`
3. 点击渲染层按钮：
   - `启动RPA模拟`
4. Playwright 会话启动后，再投送：
   - `RPA_SAMPLE_MANAGEMENT`

说明：

1. 当前模拟链路中的样品管理默认抓取 `To review + Ready to ship + Shipped + In progress + Completed`。
2. 当前支持通过 payload 指定某个 tab 或一组 tabs；未传时才按默认 5 个 tab 全抓。

## 3. 代码结构

1. Playwright 模拟入口与调度：
   - `apps/frontend.rpa.simulation/src/main/modules/ipc/rpa-controller.ts`
2. Playwright 统一模拟服务：
   - `apps/frontend.rpa.simulation/src/main/modules/rpa/playwright-simulation/playwright-simulation-service.ts`
3. 样品管理 Playwright 独立 runner：
   - `apps/frontend.rpa.simulation/src/main/modules/rpa/playwright-simulation/sample-management-playwright.ts`
4. 类型：
   - `apps/frontend.rpa.simulation/src/main/modules/rpa/sample-management/types.ts`
5. 解析与结构化逻辑：
   - `apps/frontend.rpa.simulation/src/main/modules/rpa/sample-management/parser.ts`
   - `apps/frontend.rpa.simulation/src/main/modules/rpa/sample-management/config.ts`

## 4. 当前抓取链路

执行 `RPA_SAMPLE_MANAGEMENT` 后，样品管理阶段当前流程是：

1. Playwright 统一模拟服务进入样品管理阶段。
2. 跳到样品管理页面：
   - `https://affiliate.tiktok.com/product/sample-request?shop_region=<region>`
3. 等页面表格出现；页面默认先落在 `To review`。
4. 根据 payload 决定要处理的 tab：
   - 未传 payload：依次处理 5 个 tab
   - 传 `tab` 或 `tabs`：只处理指定 tab
5. 每处理一个 tab：
   - 启动 `sample/group/list` 响应捕获
   - 如果是首个 tab 且目标是 `To review`，则重新加载当前页并直接抓首屏响应
   - 如果是首个 tab 但目标不是 `To review`，则先让页面落在默认 `To review`，再点击目标 tab 抓该 tab 的首屏响应
   - 如果不是首个 tab，则点击 tab 文本切换到对应 tab
   - 解析当前页返回的最多 50 个达人分组或请求详情
   - 每个达人下的样品请求展开成多行，每个请求单独一行
   - 如果响应 `has_more !== false`，点击分页 `Next`
   - 等下一页新的 `sample/group/list` 响应
6. `Completed` tab 额外处理：
   - 逐行点击 `View Content`
   - 打开侧边页后依次切 `Video` 与 `LIVE`
   - 捕获 `sample/performance` 响应
   - 解析内容列表并汇总到当前行的 `content_summary`
   - 点击关闭按钮收起侧边页
7. 重复处理，直到：
   - API 返回 `has_more = false`
   - 或分页 `Next` 不可点击
   - 或长时间没有新的唯一页响应
8. 指定的 tab 全部完成后导出 Excel，并保持当前 Playwright 会话继续待命。

## 5. 样品管理 API

### 5.1 分组接口

```text
GET /api/v1/affiliate/sample/group/list
```

关键点：

1. 5 个 tab 都复用同一个接口路径。
2. 当前 tab 不同，返回的数据集合不同。
3. 首屏或切 tab 后，接口都会返回当前 tab 下的最多 50 个达人分组或请求详情。
4. 每个达人分组中，可能包含多个样品请求。

### 5.2 内容绩效接口

```text
GET /api/v1/affiliate/sample/performance
```

当前仅在 `Completed` tab 使用。

关键点：

1. 点击某一行 `View Content` 后会出现侧边页。
2. 侧边页下再切 `Video` / `LIVE`，会触发对应 `content_type` 的请求。
3. `content_type=2` 视为 `video`。
4. `content_type=1` 视为 `live`。

## 6. 统一导出模型

当前每个“达人-样品请求”输出一行。

也就是说：

1. 一个达人如果有 2 个请求
2. Excel 就会落 2 行
3. `creator_id / creator_name` 相同
4. `sample_request_id / product_name / sku_*` 不同

### 6.1 行级字段

| 输出字段 | 来源路径 | 说明 |
| --- | --- | --- |
| `crawl_time` | 本地生成 | 抓取时间 ISO |
| `tab` | 当前 tab 文案 | `To review / Ready to ship / Shipped / In progress / Completed` |
| `status` | 本地补充 | 见下方 tab 状态映射 |
| `page_index` | 本地分页计数 | 第几页 API 结果 |
| `group_index` | 当前页达人分组序号 | 从 1 开始 |
| `request_index` | 当前达人下请求序号 | 从 1 开始 |
| `group_id` | `apply_group.group_id` | 达人样品申请分组 id |
| `creator_id` | `apply_group.creator_info.creator_id` 或 `apply_deatil.creator_info.creator_id` | 达人 id |
| `creator_name` | `apply_group.creator_info.name` 或 `apply_deatil.creator_info.name` | 达人账号名 |
| `sample_request_id` | `apply_infos[].apply_id` 或 `apply_deatil.apply_info.apply_id` | 样品请求 id |
| `product_name` | `product_title` | 商品标题 |
| `product_id` | `product_id` | 商品 id |
| `sku_id` | `sku_id` | SKU id |
| `sku_desc` | `sku_desc` | SKU 描述 |
| `sku_image` | `sku_image` | SKU 图片 |
| `commission_rate` | `commission_rate` | `800 -> 8`，`850 -> 8.5` |
| `commission_rate_text` | 由 `commission_rate` 转换 | `8%`、`8.5%` |
| `region` | `region` | 店铺区域，例如 `MX` |
| `sku_stock` | `sku_stock` | 当前库存 |
| `expired_in_ms` | `expired_in` | 原始毫秒值 |
| `expired_in_text` | 由 `expired_in_ms` 转换 | 例如 `6天 22小时 58分 1秒` |
| `content_summary` | `Completed` 侧边页绩效接口聚合 | JSON 字符串；非 `Completed` 默认空字符串 |

### 6.2 tab 与 status 补充值映射

| tab | 补充写入的 `status` |
| --- | --- |
| `To review` | `ready to review` |
| `Ready to ship` | `ready to ship` |
| `Shipped` | `shipped` |
| `In progress` | `content pending` |
| `Completed` | `completed` |

## 7. 各 tab 的解析说明

### 7.1 To review

1. tab 文案：`To review`
2. `status` 固定补：`ready to review`
3. 常见结构：
   - `apply_group.creator_info`
   - `apply_infos[]`
4. 一个达人可能包含多个 `apply_infos[]`，每个请求都拆成单独一行。

### 7.2 Ready to ship

1. tab 文案：`Ready to ship`
2. `status` 固定补：`ready to ship`
3. 仍然走同一接口：`sample/group/list`
4. 仍然按“每个请求一行”导出。

### 7.3 Shipped

1. tab 文案：`Shipped`
2. `status` 固定补：`shipped`
3. 常见结构：
   - `apply_deatil.apply_info`
   - `apply_deatil.creator_info`
4. 这类响应常常是一条请求详情 + 一条达人信息，同样展开为单行。

### 7.4 In progress

1. tab 文案：`In progress`
2. `status` 固定补：`content pending`
3. 常见结构：
   - `apply_deatil.apply_info`
   - `apply_deatil.creator_info`
4. 仍然按“每个请求一行”导出。

### 7.5 Completed

1. tab 文案：`Completed`
2. `status` 固定补：`completed`
3. 主表行仍然来自：`sample/group/list`
4. 当前页每一行解析完后，还会补抓 `View Content` 侧边页内容
5. `Completed` 额外产出 `content_summary`

## 8. Completed 的 `View Content` 处理

### 8.1 侧边页打开方式

当前对 `Completed` 当前页的每一行：

1. 先按当前页行序匹配可见表格行
2. 在该行内点击 `View Content`
3. 等侧边页出现

当前不依赖固定的 `arco-tabs-4-tab-*` 这类递增 id，而是按 tab 文本文案定位：

1. `Video`
2. `LIVE`

### 8.2 侧边页内部动作

打开侧边页后：

1. 捕获 `sample/performance` 请求
2. 先处理默认打开的内容请求
3. 点击 `Video`
4. 点击 `LIVE`
5. 收到对应响应后解析内容列表
6. 点击关闭按钮收起侧边页

关闭按钮当前使用：

```text
.arco-drawer-close-icon
```

### 8.3 `content_summary` JSON 结构

当前 `content_summary` 保存为 JSON 字符串，结构为：

```json
{
  "count": 2,
  "items": [
    {
      "content_type": "video",
      "content_id": "7615651699553815829",
      "cover_img": "https://...",
      "content_title": "Aceite esencial de REGALO ...",
      "content_like": 8,
      "content_order": 0,
      "content_url": "https://api.tiktokv.com/...",
      "content_view": 229,
      "comment_num": 0,
      "content_time": "2026-03-09 13:24:56"
    }
  ]
}
```

字段说明：

1. `content_type`
   - `2 -> video`
   - `1 -> live`
2. `content_id`
3. `cover_img`
4. `content_title`
   - 来自 `desc`
5. `content_like`
   - 来自 `like_num`
6. `content_order`
   - 来自 `paid_order_num`
7. `content_url`
   - 优先 `source_url`
   - 无则空字符串
8. `content_view`
   - 来自 `view_num`
9. `comment_num`
10. `content_time`
   - `video`：使用 `create_time` 转为本地时间字符串
   - `live`：如果同时有 `create_time` 与 `finish_time`，保存为 `开始时间 ~ 结束时间`

## 9. 分页停止条件

当前分页停止条件按优先级如下：

1. 当前响应明确返回 `has_more = false`
2. 分页 `Next` 已 disabled
3. 点击 `Next` 后，长时间没有新的唯一页响应
4. 安全页数上限 `200`

唯一页的判定方式：

1. 取当前页第一条达人-请求签名
2. 签名格式：`group_id|first_apply_id`
3. 如果后续响应重复同一签名，不计为新页

## 10. 导出结果

导出目录：

```text
apps/frontend.rpa.simulation/data/sample-management/
```

导出文件名：

```text
xunda_sample_management_YYYYMMDD_HHMMSS.xlsx
```

当前 workbook 保留 5 个 sheet：

1. `to_review`
2. `ready_to_ship`
3. `shipped`
4. `in_progress`
5. `completed`

## 11. 当前实现限制

1. 5 个 tab 都走同一接口路径，但实际返回结构存在差异，因此解析器同时兼容：
   - `apply_group + apply_infos[]`
   - `apply_deatil.apply_info + apply_deatil.creator_info`
   - `apply_detail.apply_info + apply_detail.creator_info`
2. `Completed` 的 `View Content` 当前按“当前页可见行序 + creator/product 文本”定位行；如果页面后续引入虚拟滚动或行结构变动，这一层需要再收紧。
3. 当前未导出 `sample/group/list` 与 `sample/performance` 的 raw JSON；若后续需要，可再补 raw 落盘。
4. 当前已支持 tab 级 payload 入口：
   - `{"tab":"completed"}`
   - `{"tabs":["to_review","completed"]}`
5. CLI 也支持直接指定 tab：
   - `sample-management completed`
   - `sample-management to_review,completed`
