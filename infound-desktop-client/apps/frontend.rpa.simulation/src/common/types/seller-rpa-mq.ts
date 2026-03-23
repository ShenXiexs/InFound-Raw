import type { SellerChatbotPayloadInput } from './rpa-chatbot'
import type { SellerCreatorDetailPayloadInput } from './rpa-creator-detail'
import type { OutreachFilterConfigInput } from './rpa-outreach'
import type { SampleManagementPayloadInput } from './rpa-sample-management'
import type { PlaywrightSimulationPayloadInput } from './rpa-simulation'

export type SellerRpaInternalQueueName = 'outreach' | 'creator_detail' | 'chat' | 'sample'

export interface SellerRpaMqMetadata {
  messageId?: string
  source?: string
  parentTaskId?: string
}

interface SellerRpaMqEnvelopeBase<
  TQueue extends SellerRpaInternalQueueName,
  TPayload
> {
  queue: TQueue
  payload: TPayload
  session?: PlaywrightSimulationPayloadInput
  metadata?: SellerRpaMqMetadata
}

export type SellerRpaOutreachMqMessage = SellerRpaMqEnvelopeBase<'outreach', OutreachFilterConfigInput>
export type SellerRpaCreatorDetailMqMessage = SellerRpaMqEnvelopeBase<
  'creator_detail',
  SellerCreatorDetailPayloadInput
>
export type SellerRpaChatMqMessage = SellerRpaMqEnvelopeBase<'chat', SellerChatbotPayloadInput>
export type SellerRpaSampleMqMessage = SellerRpaMqEnvelopeBase<'sample', SampleManagementPayloadInput>

export type SellerRpaMqMessage =
  | SellerRpaOutreachMqMessage
  | SellerRpaCreatorDetailMqMessage
  | SellerRpaChatMqMessage
  | SellerRpaSampleMqMessage
