export interface LoginStateCookieInput {
  name: string
  value: string
  domain?: string
  hostOnly?: boolean
  path?: string
  secure?: boolean
  httpOnly?: boolean
  session?: boolean
  expirationDate?: number
  sameSite?: string
}

export interface PlaywrightSimulationPayloadInput {
  region?: string
  headless?: boolean
  storageStatePath?: string
  loginState?: LoginStateCookieInput[]
  loginStatePath?: string
}

export interface PlaywrightSimulationPayload {
  region: string
  headless: boolean
  storageStatePath: string
  useStorageState: boolean
  loginState: LoginStateCookieInput[]
  useLoginState: boolean
}

export const isPlaywrightSimulationPayloadInput = (
  value: unknown
): value is PlaywrightSimulationPayloadInput => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return false
  }

  const candidate = value as Record<string, unknown>
  return (
    'region' in candidate ||
    'headless' in candidate ||
    'storageStatePath' in candidate ||
    'loginState' in candidate ||
    'loginStatePath' in candidate
  )
}
