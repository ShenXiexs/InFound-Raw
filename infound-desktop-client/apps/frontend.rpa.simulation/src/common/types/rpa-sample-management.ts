import type { SellerRpaTaskContextInput } from './seller-rpa-report'

export type SampleManagementTabKey =
  | 'to_review'
  | 'ready_to_ship'
  | 'shipped'
  | 'in_progress'
  | 'completed'

export interface SampleManagementPayload extends SellerRpaTaskContextInput {
  tabs: SampleManagementTabKey[]
}

export interface SampleManagementPayloadInput extends SellerRpaTaskContextInput {
  tab?: string
  tabs?: string[]
}
