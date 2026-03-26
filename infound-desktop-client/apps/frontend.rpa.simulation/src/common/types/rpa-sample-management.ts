import type { SellerRpaTaskContextInput } from './seller-rpa-report'

export type SampleManagementTabKey =
  | 'to_review'
  | 'ready_to_ship'
  | 'shipped'
  | 'in_progress'
  | 'completed'

export interface SampleManagementPayload extends SellerRpaTaskContextInput {
  tabs: SampleManagementTabKey[]
  script?: Record<string, unknown> | string
  scriptPath?: string
}

export interface SampleManagementPayloadInput extends SellerRpaTaskContextInput {
  tab?: string
  tabs?: string[]
  script?: Record<string, unknown> | string
  scriptPath?: string
}
