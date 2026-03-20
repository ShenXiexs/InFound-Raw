# XunDa RPA 开放要求规范（DSL 与后端解耦）

## 1. 目标

本规范用于约束 `frontend.rpa.simulation` 的后续实现方向：

1. TikTok 页面发生结构变动时，客户端改动最小化。
2. 尽量通过后端配置/规则更新修复任务，不发版或少发版。
3. 任务层统一使用可复用基础 `actionType`，避免业务专用动作泛滥。

## 2. 当前状态（截至 2026-03-11）

已完成：

1. 基础可复用动作已抽取到 DSL：
   - `goto`
   - `wait`
   - `waitForBodyText`
   - `waitForSelector`
   - `clickSelector`
   - `clickByText`
   - `fillSelector`
   - `setCheckbox`
   - `selectDropdownSingle`
   - `selectDropdownMultiple`
   - `selectCascaderOptionsByValue`
   - `fillDropdownRange`
   - `fillDropdownThreshold`
   - `pressKey`
   - `assertUrlContains`
   - `selectTab`
   - `waitForElementCount`
   - `clickPaginationNext`
   - `closeDrawer`
   - `startJsonResponseCapture`
   - `collectApiItemsByScrolling`
   - `setData`
   - `readText`
   - `assertData`
   - `waitForTextChange`
2. `RPAController` 当前保留顶层 `taskData`、任务入口、建联本地任务定义与执行触发。
3. 建联任务已开始使用“基础动作 + 通用控件动作”DSL 执行。

未完成（关键）：

1. 样品管理当前主路径已切到 5 个 tab 的 API 响应解析，`Completed` 还会补抓 `sample/performance`，不再依赖旧 DOM 展开/逐列读取主链路。
2. 样品管理字段映射与分页策略当前仍主要在客户端实现，后续继续做结构兼容收紧。
3. 后端尚未接入“远程动作配置/选择器配置/解析规则配置”。

## 3. 强制原则

1. `actionType` 仅定义浏览器基础动作或通用控件动作，不定义业务名词动作。
2. 业务编排在 `RPAController`（或后续编排层）通过 `steps` 组合实现。
3. 业务规则（选择器优先级、字段映射、解析规则、阈值）优先由后端下发。
4. 客户端只做通用执行、最小兜底与安全边界检查。

补充说明：

1. 允许新增的 DSL 应满足“跨任务复用”的要求，例如：
   - 单选下拉
   - 多选下拉
   - 级联多选
   - 区间输入
   - 阈值输入
   - checkbox 状态设置
   - 网络 JSON 响应捕获
   - 滚动加载期间的数据采集
   - 按请求方法过滤网络响应
   - 结合分页响应中的 `has_more` 判断采集终止
   - 读取文本时保留换行，便于落盘会话记录
   - 向当前聚焦输入控件派发键盘事件
2. 不允许新增的 DSL 包括：
   - `selectCreatorAgency`
   - `filterSampleToReview`
   - `chooseGmvRange`
   - 任意直接带业务语义的 actionType

## 4. 后端下发能力要求

## 4.1 任务定义下发（Task Payload）

后端应可下发：

1. `task_meta`：任务名、版本、灰度标记、过期时间。
2. `steps`：通用 DSL 动作列表（`actionType + payload + retry + onError`）。
3. `runtime_limits`：超时、最大页数、重试次数上限。
4. `feature_flags`：开关控制（例如是否抓 promotion 明细）。

## 4.2 选择器注册表（Selector Registry）

后端应可下发：

1. 每个页面块的 selector 候选列表（按优先级）。
2. 每个 selector 的适用页面版本/地区范围。
3. 失效兜底策略（候选降级顺序）。

## 4.3 字段解析规则（Parser Registry）

后端应可下发：

1. 数字解析规则（`K/M/B`、百分比、货币格式）。
2. 时间解析规则（本地时间转 UTC、区间时间格式）。
3. 文案归一化规则（状态文案映射）。

## 4.4 版本与回滚

后端应具备：

1. DSL 配置版本号（可审计）。
2. 一键回滚到上一稳定版本。
3. 按地区/账号灰度发布。

## 5. 客户端能力要求

客户端必须提供：

1. 通用动作执行引擎（已具备，持续扩充）。
2. 远程配置拉取与缓存：
   - 拉取失败使用最近成功版本。
   - 配置签名/校验失败时拒绝执行。
3. 执行观测：
   - 每个 step 的开始、成功、失败日志。
   - 错误码标准化（选择器找不到、页面超时、权限异常等）。
4. 安全边界：
   - 动作白名单，仅允许预定义 `actionType`。
   - 禁止后端下发任意 JS 直执行（或仅在强审计开关下允许）。

## 6. 样品管理下一阶段（其余 tab 补齐）

样品管理后续重点不再是旧 DOM 表格逐列解析，而是继续补齐 API 路径：

1. 继续验证 `To review / Ready to ship / Shipped / In progress` 的结构差异并补齐兼容分支。
2. 各 tab 的字段映射统一成“每个样品请求一行”的导出模型。
3. 复用现有分页 next 与 API `has_more` 终止策略。
4. 若后续新增 tab，再继续按相同 API 路径补齐。

说明：

- 当前 `To review` 已证明 API 解析链路可行。
- 后续其余 tab 优先继续沿用 API 方案，而不是回退到旧 DOM 展开抓取。

## 7. 验收标准（面向“页面变动最小客户端改动”）

满足以下条件视为达标：

1. 页面轻微 DOM 调整（类名变化、层级变化）时，仅更新后端配置即可恢复运行。
2. 客户端无需改代码的修复比例达到 70% 以上（目标值，可持续提高）。
3. 单次配置变更可在 10 分钟内完成灰度发布并生效。
4. 客户端日志可定位失败到具体 step + selector + payload。

## 8. 不在本规范范围

1. 后端具体存储选型（MySQL/Redis/Config Center）。
2. 权限系统实现细节。
3. 训练/模型评估流程。

---

维护建议：

1. 每次新增 `actionType` 必须更新本规范与 `browser-actions.ts`。
2. 每次新增后端下发字段必须补充默认值与回滚策略。
