export enum ExceptionType {
  VALIDATION = 'ValidationError',
  NETWORK = 'NetworkError',
  AUTHENTICATION = 'AuthenticationError',
  BUSINESS = 'BusinessError',
  SYSTEM = 'SystemError'
}

// 消息键的类型（确保只能使用预定义的键，避免拼写错误）
export type MessageKey =
  | 'validation.required'
  | 'validation.minAge'
  | 'network.requestFailed'
  | 'error.loginPause'
  | 'error.loginExpired'
  | 'error.loginNotExist'
  | 'error.loginErrorPassword'

// 基础异常类（适配i18n）
export class BaseException extends Error {
  public type: ExceptionType
  public code?: string
  public messageKey: MessageKey // 消息键（替代硬编码message）
  public params?: Record<string, string | number> // 消息参数
  public originalError?: Error

  constructor(type: ExceptionType, originalError: Error, messageKey: MessageKey, params?: Record<string, string | number>, code?: string) {
    // 临时使用键作为message，实际展示时会通过i18n翻译
    super(messageKey)
    Object.setPrototypeOf(this, BaseException.prototype)

    this.type = type
    this.code = code
    this.messageKey = messageKey
    this.params = params
    this.originalError = originalError

    // 捕获堆栈跟踪
    if (Error.captureStackTrace) {
      Error.captureStackTrace(this, BaseException)
    }
  }
}

export class AuthenticationException extends BaseException {
  constructor(originalError: Error, messageKey: MessageKey, params?: Record<string, string | number>, code?: string) {
    super(ExceptionType.AUTHENTICATION, originalError, messageKey, params, code)
    Object.setPrototypeOf(this, AuthenticationException.prototype)
  }
}
