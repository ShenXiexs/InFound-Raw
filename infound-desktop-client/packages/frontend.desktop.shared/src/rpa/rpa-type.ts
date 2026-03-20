// 定义支持的操作类型
import { Page } from 'playwright-core'

export type RPAActionType =
  | 'goto'
  | 'type'
  | 'click'
  | 'injectJS'
  | 'wait'
  | 'screenshot'
  | 'pressKey' // 处理快捷键 (Tab, Enter)
  | 'waitForURL' // 对应你的页面跳转等待
  | 'waitVisible' // 等待元素可见
  | 'dispatch' // 处理 dispatchEvent (如 mousedown)
  | 'clipboard' // 读取剪贴板
  | 'getText' // 获取元素文本
  | 'clickElement' // 人类化点击 (支持 Page 或 FrameLocator)
  | 'fillElement' // 逐字输入模拟 (Human-like Typing)

export type RPALocatorType =
  | 'css'
  | 'xpath'
  | 'role'
  | 'text'
  | 'label'
  | 'placeholder'
  | 'data-test'

export interface RPALocator {
  // 基础定位信息
  type: RPALocatorType
  value: string

  // 关键升级：支持链式定位 (Locator 嵌套)
  // 比如：page.locator('.wrapper').getByRole('button')
  child?: RPALocator

  // 关键升级：Playwright 过滤器 (Filters)
  filters?: {
    has?: RPALocator
    hasNot?: RPALocator
    hasText?: string | RegExp
    hasNotText?: string | RegExp
  }

  // 框架支持
  frame?: string

  // 角色相关选项 (role)
  options?: {
    name?: string | RegExp
    exact?: boolean
    level?: number
  }
}

interface BaseAction {
  id?: string
  onError?: 'abort' | 'continue' | 'retry'
  options?: { timeout?: number; retryCount?: number }
}

/*export interface RPAAction {
  actionType: RPAActionType
  locator?: RPALocator // 使用对象描述定位方式
  value?: string // type 动作的值
  script?: string // injectJS 的代码
  options?: {
    timeout?: number // 动作超时
    waitUntil?: 'load' | 'domcontentloaded' | 'networkidle' | 'commit' | undefined
    retryCount?: number
  }
  afterKey?: 'Enter' | 'Tab'
  onError?: 'abort' | 'continue' | 'retry'
}*/

// 定义每个动作独有的数据结构
export interface ClickPayload {
  locator: RPALocator
  button?: 'left' | 'right'
  clickCount?: number
}
export interface InjectJSPayload {
  script: string
  args?: any[]
}
export interface GotoPayload {
  url: string
  waitUntil?: 'load' | 'domcontentloaded' | 'networkidle' | 'commit' | undefined
}
export interface ClickElementPayload {
  locator: RPALocator
}
export interface FillElementPayload {
  locator: RPALocator
  value: string
  afterKey?: 'Enter' | 'Tab'
}

// 类型映射字典
export interface ActionPayloadMap {
  goto: GotoPayload
  // click: ClickPayload
  // injectJS: InjectJSPayload
  clickElement: ClickElementPayload
  fillElement: FillElementPayload
}

// 利用联合类型定义动作，确保每个 Action 类型都能对应到正确的 Payload
export type RPAAction = {
  [K in keyof ActionPayloadMap]: {
    actionType: K
    payload: ActionPayloadMap[K]
  } & BaseAction
}[keyof ActionPayloadMap]

// 定义最终任务协议
export interface RPATask {
  taskId: string
  taskName: string
  version: string
  config: {
    enableTrace: boolean
    retryCount: number
  }
  steps: RPAAction[]
}

// 定义执行上下文
export interface ExecutionContext {
  page: Page
  data: Record<string, any>
}
