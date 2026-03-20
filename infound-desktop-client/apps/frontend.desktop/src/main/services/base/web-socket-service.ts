import { BrowserWindow } from 'electron'
import { Client } from '@stomp/stompjs' // 使用官方 STOMP 库
import WebSocket from 'ws'
import { logger } from '../../utils/logger'
import { CookieMap, parseSetCookie } from '../../utils/set-cookie-parser'
import { AppConfig } from '@common/app-config'
import { appStore } from '../../modules/store/app-store'
import { WebSocketMessage } from '@infound/desktop-shared'
import { IPC_CHANNELS } from '@common/types/ipc-type'

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
          headers: { [tokenName.value]: tokenValue.value },
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
      heartbeatIncoming: 10000,
      heartbeatOutgoing: 10000,
      connectHeaders: {}, // 无需额外参数，认证已通过 WebSocket headers 传递
      //debug: (str) => logger.info('STOMP debug:', str), // 开发环境调试
      onConnect: () => {
        this.connected = true
        logger.info('WebSocket 连接成功')

        // 订阅公共主题
        this.client?.subscribe('/topic/notice', (msg) => {
          logger.info('收到公共广播消息:', msg.body)
          //this.sendToRenderer({ type: 'public', data: msg.body })
        })

        /*
        // 订阅私人主题
        this.client?.subscribe(
          '/user/queue/notice',
          async (msg): Promise<void> => {
            logger.info('收到私有消息:', msg.body)
            if (!msg.body) return
            const message: { [key: string]: any } = JSON.parse(msg.body)
            if (!message.messages || message.messages.length === 0) return

            const firstMessageId = message.messages[0].id
            const url = EMBED_BASE_URL + '/message.html#modal/' + firstMessageId
            await appWindowsAndViewsManager.modalWindow.openWindow(url, 500, 350)
          },
          {
            // STOMP 协议中控制 RabbitMQ 队列属性的常用 Headers
            'auto-delete': 'true', //后一个消费者断开后自动删除队列
            durable: 'false' // 队列不持久化，重启即消失，配合你的 transient_nonexcl 需求
          }
        )

        /*
        // 订阅私人主题
        this.client?.subscribe(
          '/user/queue/order',
          (msg) => {
            logger.info('收到订单消息:', msg.body)
            const order: { [key: string]: any } = JSON.parse(msg.body)
            this.sendOrderResultRenderer({ type: 'order', data: order })
          },
          {
            // STOMP 协议中控制 RabbitMQ 队列属性的常用 Headers
            'auto-delete': 'true', // 最后一个消费者断开后自动删除队列
            durable: 'false' // 队列不持久化，重启即消失，配合你的 transient_nonexcl 需求
          }
        )*/

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

  /*public registerModule(): void {
    ipcManager.registerAsync(IPCChannel.WEBSOCKET_SEND, async (message: WebSocketMessage) => {
      if (!this.connected) throw new Error('未连接')
      if (!this.client || !this.connected) {
        throw new Error('未连接到服务端')
      }
      try {
        logger.info('发送消息:', message)
        this.client.publish({
          destination: '/app/message', // 与后端 @MessageMapping 对应
          body: JSON.stringify(message)
        })
        return { success: true }
      } catch (error) {
        logger.error('发送消息失败:', error)
        throw new Error('发送消息失败')
      }
    })

    ipcManager.registerAsync(IPCChannel.WEBSOCKET_TEST, async (message: WebSocketMessage) => {
      if (!this.connected) throw new Error('未连接')
      if (!this.client || !this.connected) {
        throw new Error('未连接到服务端')
      }
      try {
        logger.info('发送消息:', message)
        this.client.publish({
          destination: '/app/test-message', // 与后端 @MessageMapping 对应
          body: JSON.stringify(message)
        })
        return { success: true }
      } catch (error) {
        logger.error('发送消息失败:', error)
        throw new Error('发送消息失败')
      }
    })

    ipcManager.registerAsync(IPCChannel.WEBSOCKET_CONNECT, async () => {
      logger.info('开始连接 WebSocket')
      await this.connect()
    })

    ipcManager.registerAsync(IPCChannel.WEBSOCKET_DISCONNECT, async () => {
      logger.info('开始断开 WebSocket')
      await this.disconnect()
    })
  }*/

  private sendToRenderer(message: WebSocketMessage): void {
    logger.info('发送到渲染进程:', message)
    const mainWindow = BrowserWindow.getFocusedWindow()
    if (mainWindow) {
      mainWindow.webContents.send(IPC_CHANNELS.RENDERER_MONITOR_WEBSOCKET_RECEIVE, message)
    }
  }

  /*private sendOrderResultRenderer(message: WebSocketMessage): void {
    logger.info('发送到渲染进程:', message)
    appWindowsAndViewsManager.embedWebContentView.broadcastOrderResultToView(message)
  }*/
}

export const webSocketService = new WebSocketService()
