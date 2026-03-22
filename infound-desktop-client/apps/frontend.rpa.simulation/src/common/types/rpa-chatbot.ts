import type { SellerRpaTaskContextInput } from './seller-rpa-report'

export interface SellerChatbotRecipient {
  creatorId: string
  message?: string
}

export interface SellerChatbotPayload extends SellerRpaTaskContextInput {
  creatorId: string
  message: string
  recipients?: SellerChatbotRecipient[]
}

export interface SellerChatbotPayloadInput extends Partial<SellerChatbotPayload> {}
