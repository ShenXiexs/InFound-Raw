import type { TaskType } from '../../main/services/task-service'

export type SellerRpaNotificationEventType =
  | 'NEW_TASK_READY'
  | 'CANCEL_TASK'

export interface SellerRpaTaskEnvelopePayload {
  [key: string]: unknown
  task?: Record<string, unknown>
  input?: Record<string, unknown>
  executor?: Record<string, unknown>
}

export interface SellerRpaNotificationPayload {
  [key: string]: unknown
  eventType: SellerRpaNotificationEventType | string
  title?: string
  type?: string
  payloadVersion?: string
  messageId?: string
  userId?: string
  taskId?: string
  taskType?: TaskType | string
  rootTaskId?: string
  cancelScope?: string
  scheduledTime?: string
  activatedAt?: string
  expiresAt?: string
  messages?: Array<Record<string, unknown>>
  payload?: SellerRpaTaskEnvelopePayload | Record<string, unknown>
}
