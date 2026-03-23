import { Client, Message } from '@stomp/stompjs' // 使用官方 STOMP 库
import WebSocket from 'ws'
import { logger } from '../../utils/logger'
import { CookieMap, parseSetCookie } from '../../utils/set-cookie-parser'
import { AppConfig } from '@common/app-config'
import { appStore } from '../../modules/store/app-store'
import { HTTP_HEADERS } from '@common/app-constants'
import { globalState } from '../../modules/state/global-state'
import { taskWorkersManager } from '../../modules/rpa/task-workers-manager'
import { TaskType } from '../task-service'

type NotificationPayload = Record<string, unknown>

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
    (payload.payload as NotificationPayload | undefined)?.task_type
  ]

  for (const candidate of candidates) {
    const normalized = String(candidate || '').trim().toUpperCase()
    if (Object.values(TaskType).includes(normalized as TaskType)) {
      return normalized as TaskType
    }
  }

  return undefined
}

// 消息类型定义
export class WebSocketService {
  private client: Client | null = null
  private connected = false
  private serverUrl = AppConfig.WS_BASE_URL

  // 建立连接（使用原生 WebSocket + STOMP）
  public async connect(): Promise<boolean> {
    // 断开现有连接
    await this.disconnect()

    const cookie = appStore.get<string>('apiCookie')
    if (!cookie) {
      logger.error('请先登录')
      return false
    }

    const cookieMap: CookieMap = parseSetCookie(cookie, { map: true })
    const tokenName = cookieMap['xunda_token_name']
    const tokenValue = cookieMap['xunda_token_value']
    if (!tokenName || !tokenValue) {
      logger.error('token 名称或值不存在')
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
            [tokenName.value]: tokenValue.value,
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
        logger.info('✅ STOMP 连接成功 - 代理已自动订阅用户专属队列')

        const userId = globalState.currentState.currentUser?.userId
        if (userId) {
          this.client?.subscribe(
            `/exchange/xunda.topic/user.notification.${userId}`,
            (message: Message) => {
              logger.info('📨 收到用户专属通知:', message.body)
              void this.handleNotificationMessage(message.body)
            },
            {
              ack: 'auto',
              durable: 'true', // ✅ 队列持久化
              'auto-delete': 'false', // ✅ 不自动删除
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

  private async handleNotificationMessage(body: string): Promise<void> {
    const payload = parseNotificationPayload(body)
    const taskType = extractTaskType(payload)
    if (taskType) {
      logger.info(`任务通知命中 taskType=${taskType}，唤醒对应 worker`)
      await taskWorkersManager.wakeUp(taskType)
      return
    }

    logger.info('任务通知未包含可识别 taskType，唤醒全部 worker')
    await taskWorkersManager.wakeUp()
  }
}

export const webSocketService = new WebSocketService()
