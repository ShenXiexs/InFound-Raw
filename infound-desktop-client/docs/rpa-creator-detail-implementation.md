# XunDa RPA 达人详细信息爬取机器人实现说明

当前文档对应的执行入口是 `apps/frontend.rpa.simulation` 中的 Playwright 模拟链路：

- [../apps/frontend.rpa.simulation/rpa-playwright-simulation-plan.md](../apps/frontend.rpa.simulation/rpa-playwright-simulation-plan.md)

说明：

1. `登录店铺` 只负责准备登录态，不负责启动达人详情机器人。
2. `启动RPA模拟` 只负责启动 Playwright 会话，不自动执行达人详情机器人。
3. 达人详情机器人当前通过单独任务指令 `RPA_SELLER_CREATOR_DETAIL` 投送到已启动的 Playwright 会话。
4. Playwright 模拟会优先使用 `data/playwright/storage-state.json`；如果文件不存在，会打开登录页等待手动登录。

## 1. 当前目标

达人详细信息机器人负责：

1. 使用预先准备好的 Playwright `storageState` 打开浏览器上下文。
2. 读取模拟 payload 中的 `shop_region`，未传时默认使用 `MX`。
3. 接到任务后跳转到：
   - `https://affiliate.tiktok.com/connection/creator/detail?cid=<creator_id>&shop_region=<region>`
4. 以页面出现 `Creator details` 作为详情页加载完成信号。
5. 在详情页内直接读取 DOM，提取达人详情、指标卡、图例分布、视频列表、相关达人。
6. 将结果导出为：
   - `data/creator-detail/seller_creator_detail_<creator_id>_<timestamp>.json`
   - `data/creator-detail/seller_creator_detail_<creator_id>_<timestamp>.csv`

说明：

1. 当前详情提取不是走接口抓包，而是走详情页 DOM 结构化提取。
2. 由于该页面字段高度可视化，当前版本按页面文案和卡片标签提取，比硬编码绝对 XPath 更稳。
3. `Release Time: 2.21.2026` 这类日期当前按 `UTC 00:00:00` 规范化为 ISO 字符串。

## 2. Playwright 模拟入口

1. 启动 `apps/frontend.rpa.simulation`。
2. 可选地准备 Playwright 登录态文件：
   - `data/playwright/storage-state.json`
3. 点击渲染层按钮：
   - `启动RPA模拟`
4. Playwright 会话启动后，再投送：
   - `RPA_SELLER_CREATOR_DETAIL`
5. 当前如果没有单独传入达人详情任务 payload，终端 demo 命令会使用 `createDemoSellerCreatorDetailPayload()`。

当前 Playwright 详情机器人任务步骤保持简洁：

1. `goto`
2. `assertUrlContains("/connection/creator/detail")`
3. `waitForBodyText("Creator details")`
4. 页面 ready 后，在主进程调用结构化 DOM 提取脚本
5. 输出 JSON / CSV

## 3. 字段规范

### 3.1 基础资料字段映射表

| 字段名 | DOM 示例 | 提取函数 | 输出字段 |
| --- | --- | --- | --- |
| 达人名 | `span[data-e2e="b7f56c3b-f013-3448"] -> _danitana` | `getDirectText(creatorNameNode)` | `creator_name` |
| 达人评分 | `span[data-e2e="74da6c4c-9b51-a49b"] -> 2.3 / 13 reviews` | `getText(ratingContainer)` + 正则 `ratingMatch` | `creator_rating` |
| 评论数 | 同上，文本含 `13 reviews` | `getText(ratingContainer)` + 正则 `reviewCountMatch` | `creator_review_count` |
| 粉丝数 | `span[data-e2e="7aed0dd7-48ba-6932"] -> 74.7K` | `getText(followerValueNode)` | `creator_followers_count` |
| MCN | `span[data-e2e="85040a36-fb50-9f7c"] -> Papaya Given Group` | `getText(mcnValueNode)` | `creator_mcn` |
| 达人简介 | `span[data-e2e="2e9732e6-4d06-458d"] -> 多行简介` | `getText(introNode, true)` | `creator_intro` |

### 3.2 指标卡字段映射表

这些字段都走统一卡片提取逻辑：

1. 先用 `findMetricCard(label)` 按卡片标题找卡片。
2. 再用 `getMetricCardValue(label)` 从卡片值区域取值。

| 字段名 | DOM 示例 | 提取函数 | 输出字段 |
| --- | --- | --- | --- |
| GMV | `span[data-e2e="61148565-2ea3-4c1b"] -> GMV`，值区 `span[data-e2e="0bc7b49d-b8b3-02d5"] -> MX$337.8 mil` | `getMetricCardValue('GMV')` | `gmv` |
| Items sold | 卡片标题 `Items sold`，值 `1.68K` | `getMetricCardValue('Items sold')` | `items_sold` |
| GPM | 卡片标题 `GPM`，值 `MX$41.8` | `getMetricCardValue('GPM')` | `gpm` |
| GMV per customer | 卡片标题 `GMV per customer`，值 `MX$234.2` | `getMetricCardValue('GMV per customer')` | `gmv_per_customer` |
| Est. post rate | 第 2 个右箭头展开后，卡片标题 `Est. post rate`，值 `61.98%` | `readMetricValue('Est. post rate')` | `est_post_rate` |
| Avg. commission rate | 卡片标题 `Avg. commission rate`，值 `8%` | `getMetricCardValue('Avg. commission rate')` | `avg_commission_rate` |
| Products | 卡片标题 `Products`，值 `103` | `getMetricCardValue('Products')` | `products` |
| Brand collaborations | 卡片标题 `Brand collaborations`，值 `9` | `getMetricCardValue('Brand collaborations')` | `brand_collaborations` |
| Video GPM | 卡片标题 `Video GPM`，值 `MX$40.5` | `getMetricCardValue('Video GPM')` | `video_gpm` |
| Videos | 卡片标题 `Videos`，值 `30` | `getMetricCardValue('Videos')` | `videos_count` |
| Avg. video views | 卡片标题 `Avg. video views`，值 `4.19K` | `getMetricCardValue('Avg. video views')` | `avg_video_views` |
| Avg. video engagement rate | 卡片标题 `Avg. video engagement rate`，值 `8.13%` | `getMetricCardValue('Avg. video engagement rate')` | `avg_video_engagement` |
| LIVE GPM | 第 3 个右箭头展开后，卡片标题 `LIVE GPM`，值 `MX$0.00` | `readMetricValue('LIVE GPM')` | `live_gpm` |
| LIVE streams | 第 3 个右箭头展开后，卡片标题 `LIVE streams`，值 `0` | `readMetricValue('LIVE streams')` | `live_streams` |
| Avg. LIVE views | 第 3 个右箭头展开后，卡片标题 `Avg. LIVE views`，值 `2` | `readMetricValue('Avg. LIVE views')` | `avg_live_views` |
| Avg. LIVE engagement rate | 卡片标题 `Avg. LIVE engagement rate`，值 `0%` | `getMetricCardValue('Avg. LIVE engagement rate')` | `avg_live_engagement` |

### 3.3 弹层与展开项字段映射表

| 字段名 | DOM 示例 | 提取函数 | 输出字段 |
| --- | --- | --- | --- |
| Top brands 列表 | 先点 `button -> View top brands`，再读 `div[data-e2e="710cdc7a-878f-599e"]` | `readTopBrands()` | `brands_list` |
| Product price | 第 1 个 `div[data-e2e="7a7839d9-8fa5-dd75"]` 展开后，卡片标题 `Product price`，值 `MX$57.4 - MX$3,963.4` | `clickArrowByIndex(0, 'Product price')` + `getMetricCardValue('Product price')` | `product_price` |
| Avg. video likes | 第 2 个右箭头展开后，卡片标题 `Avg. video likes`，值 `234` | `clickArrowByIndex(1, ['Est. post rate', 'Avg. video likes', ...])`，内部会优先点第 2 个 `ArrowRight`，并按 `data-e2e / class / xpath fallback` 重试直到指标出现 + `readMetricValue('Avg. video likes')` | `avg_video_likes` |
| Avg. video comments | 第 2 个右箭头展开后，卡片标题 `Avg. video comments`，值 `1` | `clickArrowByIndex(1, ['Est. post rate', 'Avg. video likes', ...])`，内部会优先点第 2 个 `ArrowRight`，并按 `data-e2e / class / xpath fallback` 重试直到指标出现 + `readMetricValue('Avg. video comments')` | `avg_video_comments` |
| Avg. video shares | 第 2 个右箭头展开后，卡片标题 `Avg. video shares`，值 `7` | `clickArrowByIndex(1, ['Est. post rate', 'Avg. video likes', ...])`，内部会优先点第 2 个 `ArrowRight`，并按 `data-e2e / class / xpath fallback` 重试直到指标出现 + `readMetricValue('Avg. video shares')` | `avg_video_shares` |
| LIVE GPM | 第 3 个右箭头展开后，卡片标题 `LIVE GPM`，值 `MX$0.00` | `clickArrowByIndex(2, ['LIVE GPM', 'LIVE streams', 'Avg. LIVE views'])` + `readMetricValue('LIVE GPM')` | `live_gpm` |
| LIVE streams | 第 3 个右箭头展开后，卡片标题 `LIVE streams`，值 `0` | `clickArrowByIndex(2, ['LIVE GPM', 'LIVE streams', 'Avg. LIVE views'])` + `readMetricValue('LIVE streams')` | `live_streams` |
| Avg. LIVE views | 第 3 个右箭头展开后，卡片标题 `Avg. LIVE views`，值 `2` | `clickArrowByIndex(2, ['LIVE GPM', 'LIVE streams', 'Avg. LIVE views'])` + `readMetricValue('Avg. LIVE views')` | `avg_live_views` |
| Avg. LIVE likes | 第 3 个右箭头展开后，卡片标题 `Avg. LIVE likes`，值 `0` | `clickArrowByIndex(2, ['LIVE GPM', 'LIVE streams', 'Avg. LIVE views'])` + `readMetricValue('Avg. LIVE likes')` | `avg_live_likes` |
| Avg. LIVE comments | 第 3 个右箭头展开后，卡片标题 `Avg. LIVE comments`，值 `0` | `clickArrowByIndex(2, ['LIVE GPM', 'LIVE streams', 'Avg. LIVE views'])` + `readMetricValue('Avg. LIVE comments')` | `avg_live_comments` |
| Avg. LIVE shares | 第 3 个右箭头展开后，卡片标题 `Avg. LIVE shares`，值 `0` | `clickArrowByIndex(2, ['LIVE GPM', 'LIVE streams', 'Avg. LIVE views'])` + `readMetricValue('Avg. LIVE shares')` | `avg_live_shares` |

### 3.4 Legend JSON 字段映射表

这些字段都来自 `.pcm-pc-legend.pcm-pc-legend-right`，当前按页面出现顺序映射。

| 字段名 | DOM 示例 | 提取函数 | 输出字段 |
| --- | --- | --- | --- |
| GMV per sales channel | 图例 label: `Video / Product cards`，value: `99.84% / 0.16%` | `readLegendBlock(0)` | `gmv_per_sales_channel` |
| GMV by product category | 图例 label: `Womenswear & Underwear / Beauty & Personal Care / ...` | `readLegendBlock(1)` | `gmv_by_product_category` |
| Follower gender | 图例 label: `Male / Female`，value: `25.86% / 74.14%` | `readLegendBlock(2)` | `follower_gender` |
| Follower age | 图例 label: `18 - 24 / 25 - 34 / 35-44 / 45-54 / 55+` | `readLegendBlock(3)` | `follower_age` |

### 3.5 `videos_list` 字段映射表

区块定位规则：

1. `findSectionByHeading('Videos')`
2. `collectVideoCards(sectionRoot)`
3. `parseVideoCard(card)`

| 字段名 | DOM 示例 | 提取函数 | 输出字段 |
| --- | --- | --- | --- |
| 视频标题 | `div.mb-4.text-body-m-medium -> Le cabe de todo...` | `readVideoSection('Videos') -> parseVideoCard() -> title` | `videos_list[].video_name` |
| 发布时间 | `div -> Release Time: 2.21.2026` | `readVideoSection('Videos') -> parseVideoCard() -> toUtcIso(...)` | `videos_list[].video_released_time_utc` |
| 播放量 | `div.font-semibold -> 325.2K` 的第 1 个 | `readVideoSection('Videos') -> parseVideoCard() -> metricValues[0]` | `videos_list[].video_view` |
| 点赞量 | `div.font-semibold -> 5K` 的第 2 个 | `readVideoSection('Videos') -> parseVideoCard() -> metricValues[1]` | `videos_list[].video_like` |

### 3.6 `videos_with_product` 字段映射表

区块定位规则：

1. `findSectionByHeading('Videos with product')`
2. `collectVideoCards(sectionRoot)`
3. `parseVideoCard(card)`

| 字段名 | DOM 示例 | 提取函数 | 输出字段 |
| --- | --- | --- | --- |
| 视频标题 | `div.mb-4.text-body-m-medium -> Le cabe de todo...` | `readVideoSection('Videos with product') -> parseVideoCard() -> title` | `videos_with_product[].video_name` |
| 发布时间 | `div -> Release Time: 2.21.2026` | `readVideoSection('Videos with product') -> parseVideoCard() -> toUtcIso(...)` | `videos_with_product[].video_released_time_utc` |
| 播放量 | `div.font-semibold -> 325.2K` 的第 1 个 | `readVideoSection('Videos with product') -> parseVideoCard() -> metricValues[0]` | `videos_with_product[].video_view` |
| 点赞量 | `div.font-semibold -> 5K` 的第 2 个 | `readVideoSection('Videos with product') -> parseVideoCard() -> metricValues[1]` | `videos_with_product[].video_like` |

### 3.7 `relative_creators` 字段映射表

| 字段名 | DOM 示例 | 提取函数 | 输出字段 |
| --- | --- | --- | --- |
| 相关达人名列表 | `span[data-e2e="72a4feaf-82c8-ddda"] -> mariagna_martinez` | `readRelativeCreators()` | `relative_creators[]` |

### 3.8 提取顺序说明

当前执行顺序固定为：

1. 等 `Creator details`
2. 向下滚动，触发懒加载
3. 读基础资料
4. 先读 `brands_list`
5. 先缓存当前已可见指标卡
6. 点击第 1 个右箭头后缓存 `Product price`
7. 点击第 2 个右箭头后缓存 `Est. post rate`、`Avg. video likes/comments/shares`
   - 当前不是只按索引盲点一次；
   - 会优先点击排序后的第 2 个 `ArrowRight`；
   - 如果点后指标没出现，则会用 `data-e2e="7a7839d9-8fa5-dd75"`、同类 class 选择器和 `garfish_app_for_connection_*` xpath fallback 继续重试，直到视频指标出现或重试结束。
8. 点击第 3 个右箭头后缓存 `LIVE GPM`、`LIVE streams`、`Avg. LIVE views` 等 LIVE 指标
9. 合并三次展开过程中出现过的指标卡，再统一写回字段
10. 读取 4 个 legend JSON
11. 读取 `videos_list`
12. 读取 `videos_with_product`
13. 读取 `relative_creators`

## 4. 当前输出结构

JSON 顶层结构如下：

```json
{
  "creator_id": "<creator_id_demo>",
  "region": "MX",
  "target_url": "https://affiliate.tiktok.com/connection/creator/detail?...",
  "collected_at_utc": "2026-03-11T00:00:00.000Z",
  "creator_name": "<creator_name_demo>",
  "creator_rating": "2.3",
  "creator_review_count": "13",
  "creator_followers_count": "74.7K",
  "creator_mcn": "<creator_mcn_demo>",
  "creator_intro": "...",
  "gmv": "MX$337.8 mil",
  "items_sold": "1.68K",
  "gpm": "MX$41.8",
  "gmv_per_customer": "MX$234.2",
  "est_post_rate": "61.95%",
  "avg_commission_rate": "8%",
  "products": "103",
  "brand_collaborations": "9",
  "brands_list": "<brand_a>,<brand_b>,...",
  "product_price": "MX$57.4 - MX$3,963.4",
  "video_gpm": "MX$40.5",
  "videos_count": "30",
  "avg_video_views": "4.19K",
  "avg_video_engagement": "8.13%",
  "avg_video_likes": "234",
  "avg_video_comments": "1",
  "avg_video_shares": "7",
  "live_gpm": "MX$0.00",
  "live_streams": "0",
  "avg_live_views": "2",
  "avg_live_engagement": "0%",
  "avg_live_likes": "0",
  "avg_live_comments": "0",
  "avg_live_shares": "0",
  "gmv_per_sales_channel": {},
  "gmv_by_product_category": {},
  "follower_gender": {},
  "follower_age": {},
  "videos_list": [],
  "videos_with_product": [],
  "relative_creators": []
}
```

## 5. 当前实现细节

1. 提取逻辑集中在：
   - `apps/frontend.rpa.simulation/src/main/modules/rpa/creator-detail/extractor.ts`
2. 控制器入口仍然在：
   - `apps/frontend.rpa.simulation/src/main/modules/ipc/rpa-controller.ts`
3. 页面 ready 后，主进程通过 `webContents.executeJavaScript(...)` 执行结构化提取脚本。
4. 当前会做一次页面向下滚动，用于触发懒加载区块。
5. 详情提取当前最多重试 3 次，直到至少拿到 `creator_name`。

## 6. 当前产物

每次任务结束会输出：

1. 明细 JSON
2. 单文件 CSV

说明：

1. CSV 不再分页，也不再拆多 sheet。
2. `gmv_per_sales_channel`、`gmv_by_product_category`、`follower_gender`、`follower_age`、`videos_list`、`videos_with_product`、`relative_creators` 都以 JSON 字符串写入单行 CSV。
3. 当前不再额外生成 creator-detail 的 session markdown 汇总。

## 7. 后续待补

虽然当前字段已经覆盖到用户给出的第一批完整范围，但仍有几个后续增强点：

1. 用真实页面联调校正少量 selector fallback
2. 如果图例块顺序发生变化，改成按区块标题而不是按顺序匹配
3. 如果页面继续扩出商品详情、联系方式、达人等级等字段，再在当前 JSON 结构上继续补充
