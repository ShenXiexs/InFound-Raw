import { Client, Message } from '@stomp/stompjs'
import WebSocket from 'ws'
import { logger } from '../../utils/logger'
import { CookieMap, parseSetCookie } from '../../utils/set-cookie-parser'
import { AppConfig } from '@common/app-config'
import { appStore } from '../../modules/store/app-store'
import { HTTP_HEADERS } from '@common/app-constants'
import { globalState } from '../../modules/state/global-state'
import { taskWorkersManager } from '../../modules/rpa/task-workers-manager'
import { TaskType } from '../task-service'
import { SellerRpaNotificationPayload } from '@common/types/seller-rpa-notification'

type NotificationPayload = Record<string, unknown>

const MESSAGE_CACHE_TTL_MS = 6 * 60 * 60 * 1000
const KNOWN_RPA_EVENT_TYPES = new Set(['NEW_TASK_READY', 'CANCEL_TASK', 'RPA_TASK_READY'])

const asRecord = (value: unknown): NotificationPayload | undefined =>
  value && typeof value === 'object' && !Array.isArray(value) ? (value as NotificationPayload) : undefined

const parseNotificationPayload = (body: string): NotificationPayload | undefined => {
  const text = body.trim()
  if (!text) {
    return undefined
  }

  try {
    const parsed = JSON.parse(text) as unknown
    if (parsed && typeof parsed === "object" && !Array.isArray(parsed)) {
      const root = parsed as NotificationPayload
      const firstMessage = Array.isArray(root.messages)
        ? asRecord(root.messages[0])
        : undefined
      if (!firstMessage) {
        return root
      }

      const normalized: NotificationPayload = {
        ...root,
        ...firstMessage
      }
      if (!normalized.eventType && typeof firstMessage.title === 'string') {
        normalized.eventType = firstMessage.title
      }
      if (!normalized.messageId && firstMessage.id) {
        normalized.messageId = firstMessage.id
      }
      return normalized
    }
  } catch {
    // ignore non-json body
  }

  return undefined
}

const resolveWsAuthHeader = (): { tokenName: string; tokenValue: string } | undefined => {
  const currentUser = globalState.currentState.currentUser
  const currentUserTokenName = String(currentUser?.tokenName || '').trim()
  const currentUserTokenValue = String(currentUser?.tokenValue || '').trim()
  if (currentUserTokenName && currentUserTokenValue) {
    return {
      tokenName: currentUserTokenName,
      tokenValue: currentUserTokenValue
    }
  }

  const cookie = appStore.get<string>('apiCookie')
  if (!cookie) {
    return undefined
  }

  const cookieMap: CookieMap = parseSetCookie(cookie, { map: true })
  const tokenName = cookieMap['xunda_token_name']
  const tokenValue = cookieMap['xunda_token_value']
  if (!tokenName || !tokenValue) {
    return undefined
  }

  return {
    tokenName: tokenName.value,
    tokenValue: tokenValue.value
  }
}

const toText = (value: unknown): string => {
  if (typeof value === 'string') {
    return value.trim()
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value).trim()
  }
  return ''
}

const extractTaskType = (payload?: NotificationPayload): TaskType | undefined => {
  if (!payload) {
    return undefined
  }

  const candidates = [
    payload.taskType,
    payload.task_type,
    (payload.data as NotificationPayload | undefined)?.taskType,
    (payload.data as NotificationPayload | undefined)?.task_type,
    (payload.payload as NotificationPayload | undefined)?.taskType,
    (payload.payload as NotificationPayload | undefined)?.task_type,
    ((payload.payload as NotificationPayload | undefined)?.task as NotificationPayload | undefined)?.taskType,
    ((payload.payload as NotificationPayload | undefined)?.task as NotificationPayload | undefined)?.task_type
  ]

  for (const candidate of candidates) {
    const normalized = String(candidate || '').trim().toUpperCase()
    if (Object.values(TaskType).includes(normalized as TaskType)) {
      return normalized as TaskType
    }
  }

  return undefined
}

const extractRootTaskId = (payload?: NotificationPayload): string => {
  if (!payload) {
    return ''
  }

  const candidates = [
    payload.rootTaskId,
    (payload.payload as NotificationPayload | undefined)?.rootTaskId,
    ((payload.payload as NotificationPayload | undefined)?.task as NotificationPayload | undefined)
      ?.rootTaskId,
    (
      ((payload.payload as NotificationPayload | undefined)?.input as NotificationPayload | undefined)
        ?.payload as NotificationPayload | undefined
    )?.rootTaskId
  ]

  for (const candidate of candidates) {
    const normalized = toText(candidate)
    if (normalized) {
      return normalized
    }
  }

  return ''
}

const extractCancelScope = (payload?: NotificationPayload): string => {
  if (!payload) {
    return ''
  }

  const candidates = [
    payload.cancelScope,
    (payload.payload as NotificationPayload | undefined)?.cancelScope
  ]

  for (const candidate of candidates) {
    const normalized = toText(candidate).toUpperCase()
    if (normalized) {
      return normalized
    }
  }

  return ''
}

const normalizeEventType = (payload?: NotificationPayload): string => {
  const candidates = [
    payload?.eventType,
    payload?.event_type,
    payload?.title,
    payload?.type,
    (payload?.data as NotificationPayload | undefined)?.eventType,
    (payload?.data as NotificationPayload | undefined)?.event_type,
    (payload?.data as NotificationPayload | undefined)?.title,
    (payload?.data as NotificationPayload | undefined)?.type
  ]

  for (const candidate of candidates) {
    const normalized = toText(candidate).toUpperCase()
    if (KNOWN_RPA_EVENT_TYPES.has(normalized)) {
      return normalized
    }
  }

  return ''
}

const isSellerRpaNotificationPayload = (
  payload?: NotificationPayload
): payload is SellerRpaNotificationPayload =>
  Boolean(
    payload &&
      (
        normalizeEventType(payload) ||
        extractTaskType(payload)
      )
  )

const buildUserNotificationDestination = (userId: string): string => {
  const prefix = String(AppConfig.USER_NOTIFICATION_WS_DESTINATION_PREFIX || '').trim().replace(/\/+$/, '')
  return `${prefix}.${userId}`
}

export class WebSocketService {
  private generalClient: Client | null = null
  private sellerRpaClient: Client | null = null
  private generalConnected = false
  private sellerRpaConnected = false
  private readonly processedMessageIds = new Map<string, number>()

  public async connect(): Promise<boolean> {
    await this.disconnect()

    const auth = resolveWsAuthHeader()
    if (!auth) {
      logger.error('请先登录')
      return false
    }

    const userId = globalState.currentState.currentUser?.userId
    const generalUrl = String(AppConfig.GENERAL_WS_BASE_URL || '').trim()
    const sellerRpaUrl = String(AppConfig.SELLER_RPA_WS_BASE_URL || '').trim()

    if (generalUrl) {
      this.generalClient = this.createClient({
        serverUrl: generalUrl,
        channelName: 'general',
        onConnect: (client) => {
          this.generalConnected = true
          logger.info(`✅ STOMP 连接成功: general ${generalUrl}`)
          if (userId && !sellerRpaUrl) {
            this.subscribeUserNotifications(client, userId, 'general')
          }
        }
      })
      this.generalClient.activate()
    }

    if (sellerRpaUrl) {
      this.sellerRpaClient = this.createClient({
        serverUrl: sellerRpaUrl,
        channelName: 'seller-rpa',
        onConnect: (client) => {
          this.sellerRpaConnected = true
          logger.info(`✅ STOMP 连接成功: seller-rpa ${sellerRpaUrl}`)
          if (userId) {
            this.subscribeUserNotifications(client, userId, 'seller-rpa')
          }
        }
      })
      this.sellerRpaClient.activate()
    }

    return Boolean(generalUrl || sellerRpaUrl)
  }

  private createClient(options: {
    serverUrl: string
    channelName: string
    onConnect: (client: Client) => void
  }): Client {
    const auth = resolveWsAuthHeader()
    if (!auth) {
      throw new Error('请先登录')
    }

    const client = new Client({
      webSocketFactory: () => {
        const ws = new WebSocket(options.serverUrl, {
          headers: {
            [auth.tokenName]: auth.tokenValue,
            [HTTP_HEADERS.DEVICE_TYPE]: 'client'
          },
          rejectUnauthorized: true
        })

        ws.on('close', () => {
          logger.warn(`WebSocket 已关闭，准备重新连接: ${options.channelName}`)
          try {
            ws.terminate()
          } catch {
            // ignore
          }
        })

        return ws
      },
      heartbeatIncoming: 0,
      heartbeatOutgoing: 10000,
      connectHeaders: {},
      onConnect: () => {
        options.onConnect(client)
        return true
      },
      onStompError: (frame) => {
        logger.error(`STOMP 错误[${options.channelName}]:`, frame.body)
        return false
      },
      onWebSocketError: (error) => {
        logger.error(`WebSocket 错误[${options.channelName}]:`, JSON.stringify(error))
        return false
      },
      reconnectDelay: 3000
    })
    return client
  }

  public async disconnect(): Promise<void> {
    if (this.generalClient) {
      logger.info('断开 general websocket 连接')
      await this.generalClient.deactivate()
      this.generalConnected = false
      this.generalClient = null
    }
    if (this.sellerRpaClient) {
      logger.info('断开 seller-rpa websocket 连接')
      await this.sellerRpaClient.deactivate()
      this.sellerRpaConnected = false
      this.sellerRpaClient = null
    }
  }

  public isConnected(): boolean {
    return this.generalConnected || this.sellerRpaConnected
  }

  private subscribeUserNotifications(client: Client, userId: string, channelName: string): void {
    const destination = buildUserNotificationDestination(userId)
    client.subscribe(
      destination,
      (message: Message) => {
        logger.info(`📨 收到用户通知: channel=${channelName} destination=${destination} body=${message.body}`)
        void this.handleUserNotificationMessage(message)
      },
      {
        ack: 'client-individual',
        'prefetch-count': '1'
      }
    )
  }

  private async handleUserNotificationMessage(message: Message): Promise<void> {
    const payload = parseNotificationPayload(message.body)
    if (!isSellerRpaNotificationPayload(payload)) {
      logger.info('当前用户通知不是 RPA 任务事件，直接 ack')
      message.ack()
      return
    }

    await this.handleRpaNotificationMessage(
      message,
      payload as SellerRpaNotificationPayload
    )
  }

  private async handleRpaNotificationMessage(
    message: Message,
    payload: SellerRpaNotificationPayload
  ): Promise<void> {
    const eventType = normalizeEventType(payload as NotificationPayload)
    const taskType = extractTaskType(payload as NotificationPayload)
    const messageId = toText(payload.messageId)

    if (messageId && this.isRecentlyProcessed(messageId)) {
      logger.warn(`忽略重复 RPA 任务通知: ${messageId}`)
      message.ack()
      return
    }

    const expiresAt = toText(payload?.expiresAt)
    if (expiresAt) {
      const expiresMs = Date.parse(expiresAt)
      if (Number.isFinite(expiresMs) && expiresMs <= Date.now()) {
        logger.warn(`忽略已过期 RPA 任务通知: ${messageId || '(no-message-id)'}`)
        message.ack()
        return
      }
    }

    if (eventType === 'CANCEL_TASK') {
      const taskId = toText(payload?.taskId)
      const rootTaskId = extractRootTaskId(payload)
      const cancelScope = extractCancelScope(payload)
      if (messageId) {
        this.processedMessageIds.set(messageId, Date.now())
      }
      this.compactProcessedMessageIds()
      message.ack()
      logger.warn(
        `收到 CANCEL_TASK 事件: taskType=${taskType || '(unknown)'} taskId=${taskId || '(empty)'} rootTaskId=${rootTaskId || '(empty)'} cancelScope=${cancelScope || 'TASK'}`
      )
      try {
        await taskWorkersManager.cancelTask(taskId, {
          rootTaskId,
          cancelScope
        })
      } catch (error) {
        logger.error(`处理 CANCEL_TASK 失败: ${(error as Error)?.message || error}`)
      }
      return
    }

    try {
      if (messageId) {
        this.processedMessageIds.set(messageId, Date.now())
      }
      this.compactProcessedMessageIds()
      message.ack()

      if ((eventType === 'NEW_TASK_READY' || eventType === 'RPA_TASK_READY') && taskType) {
        logger.info(
          `收到新任务触发通知，立即尝试 claim: eventType=${eventType} taskType=${taskType} taskId=${toText(payload.taskId) || '(empty)'}`
        )
        await taskWorkersManager.wakeUp(taskType)
      } else if (eventType === 'NEW_TASK_READY' || eventType === 'RPA_TASK_READY') {
        logger.info(`收到新任务触发通知但未携带 taskType，唤醒全部 worker 竞争 claim`)
        await taskWorkersManager.wakeUp()
      } else if (taskType) {
        logger.info(`任务通知命中 eventType=${eventType} taskType=${taskType}，唤醒对应 worker`)
        await taskWorkersManager.wakeUp(taskType)
      } else {
        logger.info('任务通知未包含可识别 taskType，唤醒全部 worker')
        await taskWorkersManager.wakeUp()
      }
    } catch (error) {
      logger.error(`RPA 任务通知处理失败: ${(error as Error)?.message || error}`)
    }
  }

  private isRecentlyProcessed(messageId: string): boolean {
    const processedAt = this.processedMessageIds.get(messageId)
    if (!processedAt) {
      return false
    }
    if (Date.now() - processedAt > MESSAGE_CACHE_TTL_MS) {
      this.processedMessageIds.delete(messageId)
      return false
    }
    return true
  }

  private compactProcessedMessageIds(): void {
    const threshold = Date.now() - MESSAGE_CACHE_TTL_MS
    for (const [messageId, processedAt] of this.processedMessageIds.entries()) {
      if (processedAt <= threshold) {
        this.processedMessageIds.delete(messageId)
      }
    }
  }
}

export const webSocketService = new WebSocketService()
