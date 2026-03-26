const ENV = import.meta.env

const readEnv = (...keys: string[]): string => {
  const envRecord = ENV as unknown as Record<string, string | undefined>
  for (const key of keys) {
    const value = String(envRecord[key] || '').trim()
    if (value) {
      return value
    }
  }
  return ''
}

export class AppConfig {
  public static readonly IS_PRO: boolean = ENV.MODE === 'pro'
  public static readonly LOG_LEVEL: string = ENV.VITE_LOG_LEVEL
  public static readonly LOG_ENABLE: boolean = ENV.VITE_LOG_ENABLE === 'true'
  public static readonly APP_PROTOCOL: string = ENV.VITE_APP_PROTOCOL
  public static readonly APP_HARDCODED_SALT: string = ENV.VITE_APP_HARDCODED_SALT
  public static readonly OPENAPI_BASE_URL: string = ENV.VITE_OPENAPI_BASE_URL
  public static readonly WS_BASE_URL: string = readEnv('VITE_SELLER_RPA_WS_BASE_URL', 'VITE_WS_BASE_URL')
  public static readonly SELLER_RPA_WS_INBOX_DESTINATION_PREFIX: string =
    readEnv('VITE_SELLER_RPA_WS_INBOX_DESTINATION_PREFIX') || '/amq/queue/seller.rpa.user.inbox'
  public static readonly DOWNLOAD_BASE_URL: string = ENV.VITE_DOWNLOAD_BASE_URL
  public static readonly OFFICIAL_WEBSITE_BASE_URL: string = ENV.VITE_OFFICIAL_WEBSITE_BASE_URL
  public static readonly EMBED_BASE_URL: string = ENV.VITE_EMBED_BASE_URL
  public static readonly USER_AGENT: string = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
}
