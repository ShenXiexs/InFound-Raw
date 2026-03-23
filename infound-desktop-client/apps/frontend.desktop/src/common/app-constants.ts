/** * 系统请求头常量定义
 */
export const HTTP_HEADERS = {
  DEVICE_ID: 'xunda-device-id',
  DEVICE_TYPE: 'xunda-device-type',
  APP_KEY: 'xunda-app-key',
  APP_TYPE: 'xunda-app-type',
  APP_VERSION: 'xunda-app-version',
  PAGE_ID: 'xunda-page-id',
  PAGE_CODE: 'xunda-page-code',
  PAGE_TITLE: 'xunda-page-title'
} as const

// 如果你需要把这些 Key 作为一个类型使用（例如在拦截器里限制 key 的范围）
export type HttpHeaderKey = (typeof HTTP_HEADERS)[keyof typeof HTTP_HEADERS]

//如有其它类型再添加
export const TAB_TYPES = {
  XUNDA: 'xd',
  TIKTOK: 'tk'
} as const

export const TAB_MAX_COUNT = 20

export const REGEX = {
  NUMBER: /^\d+$/,
  EMAIL: /^[a-zA-Z0-9_-]+@[a-zA-Z0-9_-]+(\.[a-zA-Z0-9_-]+)+$/,
  PHONE: /^1[3456789]\d{9}$/,
  //密码长度范围 8 ~ 16，字母、数字、特殊符号 三选二，不允许中间有空格
  PASSWORD: /^(?![a-zA-Z]+$)(?!\d+$)(?![!@#$%^&*]+$)(?![a-zA-Z\d]+$)(?![a-zA-Z!@#$%^&*]+$)(?![\d!@#$%^&*]+$)[a-zA-Z\d!@#$%^&*]{8,16}$/
} as const
