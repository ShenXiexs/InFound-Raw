/** * 系统请求头常量定义
 */
export const HTTP_HEADERS = {
  DEVICE_ID: 'xunda-device-id',
  APP_KEY: 'xunda-app-key',
  APP_TYPE: 'xunda-app-type',
  APP_VERSION: 'xunda-app-version',
  PAGE_ID: 'xunda-page-id',
  PAGE_CODE: 'xunda-page-code',
  PAGE_TITLE: 'xunda-page-title'
} as const

// 如果你需要把这些 Key 作为一个类型使用（例如在拦截器里限制 key 的范围）
export type HttpHeaderKey = (typeof HTTP_HEADERS)[keyof typeof HTTP_HEADERS]
