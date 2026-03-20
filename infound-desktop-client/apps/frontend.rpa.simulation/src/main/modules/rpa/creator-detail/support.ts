import type {
  SellerCreatorDetailData,
  SellerCreatorDetailPayload,
  SellerCreatorDetailPayloadInput
} from '@common/types/rpa-creator-detail'
import type { BrowserAction } from '../task-dsl/browser-actions'

export const SELLER_CREATOR_DETAIL_READY_TEXT = 'Creator details'

const createDefaultSellerCreatorDetailPayload = (): SellerCreatorDetailPayload => ({
  creatorId: ''
})

export const createDemoSellerCreatorDetailPayload = (): SellerCreatorDetailPayloadInput => ({
  creatorId: '<creator_id_demo>'
})

export const mergeSellerCreatorDetailPayload = (
  input?: SellerCreatorDetailPayloadInput
): SellerCreatorDetailPayload => {
  const defaults = createDefaultSellerCreatorDetailPayload()
  return {
    creatorId: String(input?.creatorId ?? defaults.creatorId).trim()
  }
}

export const isSellerCreatorDetailPayloadInput = (value: unknown): value is SellerCreatorDetailPayloadInput => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  return 'creatorId' in (value as Record<string, unknown>)
}

export const countCollectedCreatorDetailFields = (detail: SellerCreatorDetailData): number =>
  Object.values(detail).reduce((count, value) => {
    if (Array.isArray(value)) {
      return count + (value.length > 0 ? 1 : 0)
    }
    if (value && typeof value === 'object') {
      return count + (Object.keys(value as Record<string, unknown>).length > 0 ? 1 : 0)
    }
    return count + (String(value ?? '').trim() ? 1 : 0)
  }, 0)

export const buildSellerCreatorDetailSteps = (): BrowserAction[] => [
  {
    actionType: 'waitForBodyText',
    payload: {
      text: SELLER_CREATOR_DETAIL_READY_TEXT,
      timeoutMs: 30000,
      intervalMs: 500
    },
    options: { retryCount: 5 },
    onError: 'abort'
  }
]
