import type { SellerRpaTaskContextInput } from './seller-rpa-report'

export interface SellerChatbotPayload extends SellerRpaTaskContextInput {
  creatorId: string
  message: string
}

export interface SellerChatbotPayloadInput extends Partial<SellerChatbotPayload> {}
