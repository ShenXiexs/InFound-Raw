import type { TaskType } from '../../main/services/task-service'

export type SellerRpaNotificationEventType = 'NEW_TASK_READY' | 'CANCEL_TASK'

export interface SellerRpaNotificationPayload {
  [key: string]: unknown
  eventType: SellerRpaNotificationEventType
  messageId?: string
  taskId?: string
  taskType?: TaskType | string
  rootTaskId?: string
  cancelScope?: string
  expiresAt?: string
  userId?: string
  payloadVersion?: string
  scheduledTime?: string
  activatedAt?: string
}
