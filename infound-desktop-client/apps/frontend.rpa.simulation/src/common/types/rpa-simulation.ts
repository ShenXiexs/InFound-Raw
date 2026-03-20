export interface PlaywrightSimulationPayloadInput {
  region?: string
  headless?: boolean
  storageStatePath?: string
}

export interface PlaywrightSimulationPayload {
  region: string
  headless: boolean
  storageStatePath: string
  useStorageState: boolean
}

export const isPlaywrightSimulationPayloadInput = (
  value: unknown
): value is PlaywrightSimulationPayloadInput => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) {
    return false
  }

  const candidate = value as Record<string, unknown>
  return 'region' in candidate || 'headless' in candidate || 'storageStatePath' in candidate
}
