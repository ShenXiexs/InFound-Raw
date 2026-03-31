const ENV = import.meta.env

export class AppConfig {
  public static readonly IS_PRO: boolean = ENV.MODE === 'pro'
  public static readonly LOG_LEVEL: string = ENV.VITE_LOG_LEVEL
  public static readonly LOG_ENABLE: boolean = ENV.VITE_LOG_ENABLE === 'true'
  public static readonly APP_PROTOCOL: string = ENV.VITE_APP_PROTOCOL
  public static readonly APP_HARDCODED_SALT: string = ENV.VITE_APP_HARDCODED_SALT
  public static readonly OPENAPI_BASE_URL: string = ENV.VITE_OPENAPI_BASE_URL
  public static readonly SELLER_RPA_WS_BASE_URL: string = ENV.VITE_SELLER_RPA_WS_BASE_URL
  public static readonly USER_NOTIFICATION_WS_DESTINATION_PREFIX: string =
    ENV.VITE_USER_NOTIFICATION_WS_DESTINATION_PREFIX || '/amq/queue/user.notification'
  public static readonly TASK_MANAGER_POLLING_INTERVAL_MS: number = Math.max(
    Number(ENV.VITE_TASK_MANAGER_POLLING_INTERVAL_MS || '20000') || 20000,
    1000
  )
  public static readonly DOWNLOAD_BASE_URL: string = ENV.VITE_DOWNLOAD_BASE_URL
  public static readonly OFFICIAL_WEBSITE_BASE_URL: string = ENV.VITE_OFFICIAL_WEBSITE_BASE_URL
  public static readonly EMBED_BASE_URL: string = ENV.VITE_EMBED_BASE_URL
  public static readonly USER_AGENT: string = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
}
