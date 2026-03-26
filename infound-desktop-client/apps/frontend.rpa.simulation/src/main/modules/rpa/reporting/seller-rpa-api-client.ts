import type { SellerRpaReportConfigInput } from '@sim-common/types/seller-rpa-report'

interface LoggerLike {
  info(message: string, ...args: unknown[]): void
  warn(message: string, ...args: unknown[]): void
  error(message: string, ...args: unknown[]): void
}

export interface ResolvedSellerRpaReportConfig {
  baseUrl: string
  authToken: string
  authHeader: string
}

const DEFAULT_AUTH_HEADER = 'INFoundSellerAuth'
const REQUEST_TIMEOUT_MS = 30000

const readEnv = (...keys: string[]): string => {
  for (const key of keys) {
    const value = String(process.env[key] || '').trim()
    if (value) return value
  }
  return ''
}

const normalizeBaseUrl = (value: string): string => value.replace(/\/+$/, '')

const withTimeoutSignal = (timeoutMs: number): AbortSignal => {
  const controller = new AbortController()
  setTimeout(() => controller.abort(), timeoutMs).unref?.()
  return controller.signal
}

export const resolveSellerRpaReportConfig = (
  input?: SellerRpaReportConfigInput
): ResolvedSellerRpaReportConfig | null => {
  const enabled = input?.enabled ?? true
  if (!enabled) {
    return null
  }

  const baseUrl = String(
    input?.baseUrl ||
      readEnv('SELLER_RPA_API_BASE_URL', 'VITE_SELLER_RPA_API_BASE_URL')
  ).trim()
  const authToken = String(
    input?.authToken ||
      readEnv('SELLER_RPA_API_TOKEN', 'VITE_SELLER_RPA_API_TOKEN')
  ).trim()

  if (!baseUrl || !authToken) {
    return null
  }

  const authHeader = String(
    input?.authHeader ||
      readEnv('SELLER_RPA_API_AUTH_HEADER', 'VITE_SELLER_RPA_API_AUTH_HEADER') ||
      DEFAULT_AUTH_HEADER
  ).trim()

  return {
    baseUrl: normalizeBaseUrl(baseUrl),
    authToken,
    authHeader: authHeader || DEFAULT_AUTH_HEADER
  }
}

export class SellerRpaApiClient {
  public static create(
    logger: LoggerLike,
    input?: SellerRpaReportConfigInput
  ): SellerRpaApiClient | null {
    const config = resolveSellerRpaReportConfig(input)
    if (!config) {
      return null
    }
    return new SellerRpaApiClient(logger, config)
  }

  private constructor(
    private readonly logger: LoggerLike,
    private readonly config: ResolvedSellerRpaReportConfig
  ) {}

  public async reportOutreachResults(payload: Record<string, unknown>): Promise<void> {
    await this.post('/api/v1/rpa/outreach/results', payload)
  }

  public async reportCreatorDetailResults(payload: Record<string, unknown>): Promise<void> {
    await this.post('/api/v1/rpa/creator-details/results', payload)
  }

  public async reportSampleMonitorResults(payload: Record<string, unknown>): Promise<void> {
    await this.post('/api/v1/rpa/sample-monitor/results', payload)
  }

  private async post(path: string, payload: Record<string, unknown>): Promise<void> {
    const url = `${this.config.baseUrl}${path}`
    const response = await fetch(url, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Accept: 'application/json',
        [this.config.authHeader]: this.config.authToken
      },
      body: JSON.stringify(payload),
      signal: withTimeoutSignal(REQUEST_TIMEOUT_MS)
    })

    const responseText = await response.text()
    if (!response.ok) {
      this.logger.error(
        `Seller backend 回传失败: status=${response.status} path=${path} body=${responseText || '(empty)'}`
      )
      throw new Error(`seller backend report failed: ${response.status} ${path}`)
    }

    this.logger.info(`Seller backend 回传成功: path=${path}`)
  }
}
