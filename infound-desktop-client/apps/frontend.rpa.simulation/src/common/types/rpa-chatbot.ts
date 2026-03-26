import type { SellerRpaTaskContextInput } from './seller-rpa-report'

export interface SellerChatbotRecipient {
  creatorId: string
  message?: string
}

export interface SellerChatbotPayload extends SellerRpaTaskContextInput {
  creatorId: string
  message: string
  recipients?: SellerChatbotRecipient[]
  script?: Record<string, unknown> | string
  scriptPath?: string
}

export interface SellerChatbotPayloadInput extends Partial<SellerChatbotPayload> {}
