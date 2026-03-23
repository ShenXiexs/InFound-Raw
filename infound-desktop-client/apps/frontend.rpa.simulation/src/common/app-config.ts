const ENV = import.meta.env

const readRuntimeEnv = (...keys: string[]): string => {
  const envRecord = ENV as unknown as Record<string, string | undefined>
  for (const key of keys) {
    const viteValue = String(envRecord[key] || '').trim()
    if (viteValue) {
      return viteValue
    }
    const processValue = String(process.env[key] || '').trim()
    if (processValue) {
      return processValue
    }
  }
  return ''
}

const toBoolean = (value: string, defaultValue: boolean): boolean => {
  const normalized = value.trim().toLowerCase()
  if (!normalized) {
    return defaultValue
  }
  if (['1', 'true', 'yes', 'y', 'on'].includes(normalized)) {
    return true
  }
  if (['0', 'false', 'no', 'n', 'off'].includes(normalized)) {
    return false
  }
  return defaultValue
}

const toInteger = (value: string, defaultValue: number): number => {
  const numeric = Number(value)
  if (!Number.isFinite(numeric)) {
    return defaultValue
  }
  return Math.max(Math.trunc(numeric), 0)
}

const deriveSellerRpaWsBaseUrl = (): string => {
  const explicit = readRuntimeEnv('VITE_SELLER_RPA_WS_BASE_URL', 'SELLER_RPA_WS_BASE_URL')
  if (explicit) {
    return explicit
  }

  const apiBaseUrl = readRuntimeEnv('VITE_SELLER_RPA_API_BASE_URL', 'SELLER_RPA_API_BASE_URL')
  if (!apiBaseUrl) {
    return ''
  }

  const trimmed = apiBaseUrl.replace(/\/+$/, '')
  if (/^wss?:\/\//i.test(trimmed)) {
    return trimmed.endsWith('/ws') ? trimmed : `${trimmed}/ws`
  }
  if (/^https?:\/\//i.test(trimmed)) {
    const protocol = trimmed.startsWith('https://') ? 'wss://' : 'ws://'
    const suffix = trimmed.replace(/^https?:\/\//i, '')
    return suffix.endsWith('/ws') ? `${protocol}${suffix}` : `${protocol}${suffix}/ws`
  }
  return ''
}

export class AppConfig {
  public static readonly IS_PRO: boolean = ENV.MODE === 'pro'
  public static readonly LOG_LEVEL: string = ENV.VITE_LOG_LEVEL
  public static readonly LOG_ENABLE: boolean = ENV.VITE_LOG_ENABLE === 'true'
  public static readonly USER_AGENT: string = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
  public static readonly SELLER_RPA_API_BASE_URL: string = readRuntimeEnv(
    'VITE_SELLER_RPA_API_BASE_URL',
    'SELLER_RPA_API_BASE_URL'
  )
  public static readonly SELLER_RPA_API_AUTH_HEADER: string = readRuntimeEnv(
    'VITE_SELLER_RPA_API_AUTH_HEADER',
    'SELLER_RPA_API_AUTH_HEADER'
  )
  public static readonly SELLER_RPA_API_TOKEN: string = readRuntimeEnv(
    'VITE_SELLER_RPA_API_TOKEN',
    'SELLER_RPA_API_TOKEN'
  )
  public static readonly SELLER_RPA_WS_ENABLED: boolean = toBoolean(
    readRuntimeEnv('VITE_SELLER_RPA_WS_ENABLED', 'SELLER_RPA_WS_ENABLED'),
    true
  )
  public static readonly SELLER_RPA_DEBUG_INBOX_ENABLED: boolean = toBoolean(
    readRuntimeEnv('VITE_SELLER_RPA_DEBUG_INBOX_ENABLED', 'SELLER_RPA_DEBUG_INBOX_ENABLED'),
    false
  )
  public static readonly SELLER_RPA_WS_BASE_URL: string = deriveSellerRpaWsBaseUrl()
  public static readonly SELLER_RPA_WS_AUTH_HEADER: string =
    readRuntimeEnv(
      'VITE_SELLER_RPA_WS_AUTH_HEADER',
      'SELLER_RPA_WS_AUTH_HEADER',
      'VITE_SELLER_RPA_API_AUTH_HEADER',
      'SELLER_RPA_API_AUTH_HEADER'
    ) || 'INFoundSellerAuth'
  public static readonly SELLER_RPA_WS_TOKEN: string = readRuntimeEnv(
    'VITE_SELLER_RPA_WS_TOKEN',
    'SELLER_RPA_WS_TOKEN',
    'VITE_SELLER_RPA_API_TOKEN',
    'SELLER_RPA_API_TOKEN'
  )
  public static readonly SELLER_RPA_WS_USER_ID: string = readRuntimeEnv(
    'VITE_SELLER_RPA_WS_USER_ID',
    'SELLER_RPA_WS_USER_ID',
    'SELLER_USER_ID'
  )
  public static readonly SELLER_RPA_WS_INBOX_DESTINATION: string = readRuntimeEnv(
    'VITE_SELLER_RPA_WS_INBOX_DESTINATION',
    'SELLER_RPA_WS_INBOX_DESTINATION'
  )
  public static readonly SELLER_RPA_WS_RECONNECT_DELAY_MS: number = toInteger(
    readRuntimeEnv('VITE_SELLER_RPA_WS_RECONNECT_DELAY_MS', 'SELLER_RPA_WS_RECONNECT_DELAY_MS'),
    3000
  )
  public static readonly SELLER_RPA_WS_HEARTBEAT_INCOMING_MS: number = toInteger(
    readRuntimeEnv(
      'VITE_SELLER_RPA_WS_HEARTBEAT_INCOMING_MS',
      'SELLER_RPA_WS_HEARTBEAT_INCOMING_MS'
    ),
    10000
  )
  public static readonly SELLER_RPA_WS_HEARTBEAT_OUTGOING_MS: number = toInteger(
    readRuntimeEnv(
      'VITE_SELLER_RPA_WS_HEARTBEAT_OUTGOING_MS',
      'SELLER_RPA_WS_HEARTBEAT_OUTGOING_MS'
    ),
    10000
  )
}
