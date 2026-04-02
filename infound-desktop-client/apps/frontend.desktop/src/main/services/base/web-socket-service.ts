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
import { SellerRpaNotificationEventType, SellerRpaNotificationPayload } from '@common/types/seller-rpa-notification'

const MESSAGE_CACHE_TTL_MS = 6 * 60 * 60 * 1000
const KNOWN_RPA_EVENT_TYPES = new Set<SellerRpaNotificationEventType>(['NEW_TASK_READY', 'CANCEL_TASK'])

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

const normalizeEventType = (value: unknown): SellerRpaNotificationEventType | undefined => {
  const normalized = toText(value).toUpperCase()
  if (KNOWN_RPA_EVENT_TYPES.has(normalized as SellerRpaNotificationEventType)) {
    return normalized as SellerRpaNotificationEventType
  }
  return undefined
}

const parseNotificationPayload = (body: string): SellerRpaNotificationPayload | undefined => {
  const text = body.trim()
  if (!text) {
    return undefined
  }

  try {
    const parsed = JSON.parse(text) as unknown
    if (!parsed || typeof parsed !== 'object' || Array.isArray(parsed)) {
      return undefined
    }
    const payload = parsed as SellerRpaNotificationPayload
    const eventType = normalizeEventType(payload.eventType)
    if (!eventType) {
      return undefined
    }
    return {
      ...payload,
      eventType
    }
  } catch {
    return undefined
  }
}

const extractTaskType = (payload?: SellerRpaNotificationPayload): TaskType | undefined => {
  const normalized = toText(payload?.taskType).toUpperCase()
  if (Object.values(TaskType).includes(normalized as TaskType)) {
    return normalized as TaskType
  }
  return undefined
}

const extractRootTaskId = (payload?: SellerRpaNotificationPayload): string => toText(payload?.rootTaskId)

const extractCancelScope = (payload?: SellerRpaNotificationPayload): string => toText(payload?.cancelScope).toUpperCase()

const buildUserNotificationDestination = (userId: string): string => {
  const prefix = String(AppConfig.USER_NOTIFICATION_WS_DESTINATION_PREFIX || '')
    .trim()
    .replace(/\/+$/, '')
  return `${prefix}.${userId}`
}

const formatWebSocketError = (error: unknown): string => {
  if (error instanceof Error) {
    return error.stack || error.message
  }

  if (error && typeof error === 'object') {
    const candidate = error as Record<string, unknown>
    const eventMessage = String(candidate.message || '').trim()
    const nestedError = candidate.error
    if (nestedError instanceof Error) {
      return nestedError.stack || nestedError.message
    }
    if (eventMessage) {
      return eventMessage
    }
    try {
      const json = JSON.stringify(error)
      if (json && json !== '{}') {
        return json
      }
    } catch {
      // ignore
    }
  }

  return String(error)
}

export class WebSocketService {
  private client: Client | null = null
  private readonly processedMessageIds = new Map<string, number>()

  public async connect(): Promise<boolean> {
    await this.disconnect()

    const auth = resolveWsAuthHeader()
    if (!auth) {
      logger.error('请先登录')
      return false
    }

    const userId = globalState.currentState.currentUser?.userId
    const serverUrl = String(AppConfig.SELLER_RPA_WS_BASE_URL || '').trim()

    if (!serverUrl) {
      logger.error('Seller RPA WebSocket 地址未配置')
      return false
    }

    this.client = this.createClient({
      serverUrl,
      onConnect: (client) => {
        logger.info(`✅ STOMP 连接成功: ${serverUrl}`)
        if (userId) {
          this.subscribeUserNotifications(client, userId)
        }
      }
    })
    this.client.activate()

    return true
  }

  private createClient(options: { serverUrl: string; onConnect: (client: Client) => void }): Client {
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
          logger.warn(`WebSocket 已关闭，准备重新连接: ${options.serverUrl}`)
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
        logger.error(`STOMP 错误: message=${frame.headers.message || ''} body=${frame.body || ''}`)
        return false
      },
      onWebSocketError: (error) => {
        logger.error(`WebSocket 错误: url=${options.serverUrl} detail=${formatWebSocketError(error)}`)
        return false
      },
      reconnectDelay: 3000
    })
    return client
  }

  public async disconnect(): Promise<void> {
    if (this.client) {
      logger.info('断开 websocket 连接')
      await this.client.deactivate()
      this.client = null
    }
  }

  private subscribeUserNotifications(client: Client, userId: string): void {
    const destination = buildUserNotificationDestination(userId)
    client.subscribe(
      destination,
      (message: Message) => {
        logger.info(`📨 收到用户通知: destination=${destination} body=${message.body}`)
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
    if (!payload) {
      logger.info('当前用户通知不是 RPA 任务事件，直接 ack')
      message.ack()
      return
    }

    await this.handleRpaNotificationMessage(message, payload)
  }

  private async handleRpaNotificationMessage(message: Message, payload: SellerRpaNotificationPayload): Promise<void> {
    const eventType = payload.eventType
    const taskType = extractTaskType(payload)
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

      if (eventType === 'NEW_TASK_READY' && taskType) {
        logger.info(`收到新任务触发通知，立即尝试 claim: eventType=${eventType} taskType=${taskType} taskId=${toText(payload.taskId) || '(empty)'}`)
        await taskWorkersManager.wakeUp(taskType)
      } else if (eventType === 'NEW_TASK_READY') {
        logger.info(`收到新任务触发通知但未携带 taskType，唤醒全部 worker 竞争 claim`)
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
