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
}
