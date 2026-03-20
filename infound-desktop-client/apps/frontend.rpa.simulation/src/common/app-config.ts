const ENV = import.meta.env

export class AppConfig {
  public static readonly IS_PRO: boolean = ENV.MODE === 'pro'
  public static readonly LOG_LEVEL: string = ENV.VITE_LOG_LEVEL
  public static readonly LOG_ENABLE: boolean = ENV.VITE_LOG_ENABLE === 'true'
  public static readonly USER_AGENT: string = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.0.0 Safari/537.36'
}
