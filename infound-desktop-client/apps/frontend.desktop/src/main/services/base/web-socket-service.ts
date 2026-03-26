import { Client, Message } from '@stomp/stompjs' // 使用官方 STOMP 库
import WebSocket from 'ws'
import { logger } from '../../utils/logger'
import { CookieMap, parseSetCookie } from '../../utils/set-cookie-parser'
import { AppConfig } from '@common/app-config'
import { appStore } from '../../modules/store/app-store'
import { HTTP_HEADERS } from '@common/app-constants'
import { globalState } from '../../modules/state/global-state'
import { taskWorkersManager } from '../../modules/rpa/task-workers-manager'
import { TaskInfo, TaskStatus, TaskType } from '../task-service'
import { SellerRpaNotificationPayload } from '@common/types/seller-rpa-notification'

type NotificationPayload = Record<string, unknown>
const MESSAGE_CACHE_TTL_MS = 6 * 60 * 60 * 1000

const parseNotificationPayload = (body: string): NotificationPayload | undefined => {
  const text = body.trim()
  if (!text) {
    return undefined
  }
  try {
    const parsed = JSON.parse(text) as unknown
    if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
      return parsed as NotificationPayload
    }
  } catch {
    /* non-json notification */
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

const normalizeEventType = (payload?: NotificationPayload): string => {
  return String(
    payload?.eventType ||
      payload?.event_type ||
      (payload?.data as NotificationPayload | undefined)?.eventType ||
      ''
  )
    .trim()
    .toUpperCase()
}

const asRecord = (value: unknown): NotificationPayload | undefined =>
  value && typeof value === 'object' && !Array.isArray(value) ? (value as NotificationPayload) : undefined

const toText = (value: unknown): string => {
  if (typeof value === 'string') {
    return value.trim()
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value).trim()
  }
  return ''
}

const resolveTaskEnvelope = (payload?: NotificationPayload): NotificationPayload | undefined => {
  const envelope = asRecord(payload?.payload)
  if (!envelope) {
    return undefined
  }
  if ('task' in envelope || 'input' in envelope || 'executor' in envelope) {
    return envelope
  }
  return undefined
}

const buildTaskInfoFromNotification = (
  payload?: SellerRpaNotificationPayload
): TaskInfo | undefined => {
  const taskType = extractTaskType(payload)
  const envelope = resolveTaskEnvelope(payload as NotificationPayload | undefined)
  if (!taskType || !envelope) {
    return undefined
  }

  const taskNode = asRecord(envelope.task) || {}
  const taskId = toText(payload?.taskId) || toText(taskNode.taskId)
  if (!taskId) {
    return undefined
  }

  const nowIso = new Date().toISOString()
  const scheduledTime = toText(payload?.scheduledTime) || toText(taskNode.scheduledTime)
  const createdAt = toText(taskNode.createdAt) || scheduledTime || nowIso
  const updatedAt =
    toText(taskNode.updatedAt) ||
    toText(payload?.activatedAt) ||
    scheduledTime ||
    nowIso

  return {
    id: taskId,
    task_type: taskType,
    task_status: TaskStatus.Pending,
    task_data: envelope,
    created_at: createdAt,
    updated_at: updatedAt,
    task_source: 'inbox'
  }
}

const buildSellerNotificationDestination = (userId: string): string => {
  const prefix = String(AppConfig.SELLER_RPA_WS_INBOX_DESTINATION_PREFIX || '').trim().replace(/\/+$/, '')
  return `${prefix}.${userId}`
}

// 消息类型定义
export class WebSocketService {
  private client: Client | null = null
  private connected = false
  private serverUrl = AppConfig.WS_BASE_URL
  private readonly processedMessageIds = new Map<string, number>()

  // 建立连接（使用原生 WebSocket + STOMP）
  public async connect(): Promise<boolean> {
    // 断开现有连接
    await this.disconnect()

    const auth = resolveWsAuthHeader()
    if (!auth) {
      logger.error('请先登录')
      return false
    }

    /*// 创建原生 WebSocket 连接（支持自定义 headers）
    const ws = new WebSocket(this.serverUrl, {
      headers: {
        [tokenName.value]: tokenValue.value
      },
      rejectUnauthorized: true
    })*/

    // 初始化 STOMP 客户端
    this.client = new Client({
      webSocketFactory: () => {
        const ws = new WebSocket(this.serverUrl, {
          headers: {
            [auth.tokenName]: auth.tokenValue,
            [HTTP_HEADERS.DEVICE_TYPE]: 'client'
          },
          rejectUnauthorized: true
        })

        ws.on('close', () => {
          logger.warn('WebSocket 已关闭，准备重新连接')
          try {
            ws.terminate()
          } catch {
            /* empty */
          }
        })

        return ws
      }, // 使用原生 WebSocket 实例
      heartbeatIncoming: 0,
      heartbeatOutgoing: 10000,
      connectHeaders: {}, // 无需额外参数，认证已通过 WebSocket headers 传递
      //debug: (str) => logger.info('STOMP debug:', str), // 开发环境调试
      onConnect: () => {
        this.connected = true
        logger.info('✅ STOMP 连接成功 - 已订阅 seller RPA 用户收件箱')

        const userId = globalState.currentState.currentUser?.userId
        if (userId) {
          const destination = buildSellerNotificationDestination(userId)
          this.client?.subscribe(
            destination,
            (message: Message) => {
              logger.info(`📨 收到 seller RPA 通知: destination=${destination} body=${message.body}`)
              void this.handleNotificationMessage(message)
            },
            {
              ack: 'client-individual',
              durable: 'true', // ✅ 队列持久化
              'auto-delete': 'false', // ✅ 不自动删除
              'prefetch-count': '1',
              'x-declare': JSON.stringify({
                durable: true,
                autoDelete: false
              })
            }
          )
        }

        return true
      },
      onStompError: (frame) => {
        logger.error('STOMP 错误:', frame.body)
        return false
      },
      onWebSocketError: (error) => {
        logger.error('WebSocket 错误:', JSON.stringify(error))
        return false
      },
      reconnectDelay: 3000 // 自动重连间隔（3秒）
    })

    // 启动连接
    this.client.activate()

    return true
  }

  public async disconnect(): Promise<void> {
    if (this.client) {
      logger.info('断开连接')
      await this.client.deactivate() // 关闭 STOMP 连接
      this.connected = false
      this.client = null
    }
  }

  public isConnected(): boolean {
    return this.connected
  }

  private async handleNotificationMessage(message: Message): Promise<void> {
    const payload = parseNotificationPayload(message.body) as SellerRpaNotificationPayload | undefined
    const eventType = normalizeEventType(payload)
    const taskType = extractTaskType(payload)
    const messageId = toText(payload?.messageId)

    if (messageId && this.isRecentlyProcessed(messageId)) {
      logger.warn(`忽略重复 seller RPA 消息: ${messageId}`)
      message.ack()
      return
    }

    const expiresAt = toText(payload?.expiresAt)
    if (expiresAt) {
      const expiresMs = Date.parse(expiresAt)
      if (Number.isFinite(expiresMs) && expiresMs <= Date.now()) {
        logger.warn(`忽略已过期 seller RPA 消息: ${messageId || '(no-message-id)'}`)
        message.ack()
        return
      }
    }

    if (eventType === 'CANCEL_TASK') {
      logger.warn(
        `收到 CANCEL_TASK 事件，但当前 desktop 仅记录日志，尚未实现运行中任务取消: taskType=${taskType || '(unknown)'}`
      )
      message.ack()
      return
    }

    try {
      const directTask = buildTaskInfoFromNotification(payload)
      if (directTask) {
        logger.info(
          `任务通知命中完整 payload，直接分发执行: eventType=${eventType || 'NEW_TASK_READY'} taskType=${directTask.task_type} taskId=${directTask.id}`
        )
        await taskWorkersManager.enqueueTask(directTask)
      } else if ((eventType === 'NEW_TASK_READY' || eventType === 'RPA_TASK_READY') && taskType) {
        logger.info(`任务通知命中 eventType=${eventType} taskType=${taskType}，唤醒对应 worker`)
        await taskWorkersManager.wakeUp(taskType)
      } else if (taskType) {
        logger.info(`任务通知命中 taskType=${taskType}，唤醒对应 worker`)
        await taskWorkersManager.wakeUp(taskType)
      } else {
        logger.info('任务通知未包含可识别 taskType，唤醒全部 worker')
        await taskWorkersManager.wakeUp()
      }

      if (messageId) {
        this.processedMessageIds.set(messageId, Date.now())
      }
      this.compactProcessedMessageIds()
      message.ack()
    } catch (error) {
      logger.error(
        `seller RPA 通知处理失败: ${(error as Error)?.message || error}`
      )
      if (typeof message.nack === 'function') {
        message.nack()
      } else {
        message.ack()
      }
      return
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
