import { ipcMain } from 'electron'
import { IPC_GATEWAY_KEY, IPC_METHOD_KEY, IPC_TYPE_KEY, IPCType } from './ipc-decorator'
import { logger } from '../../../utils/logger'

export class IPCManager {
  private static gatewayHandlers = new Map<string, Map<string, (...args: any[]) => any>>()

  private static senders = new Set<string>()

  public static register(controller: any): void {
    const proto = Object.getPrototypeOf(controller)
    Object.getOwnPropertyNames(proto).forEach((methodName) => {
      const gateway = Reflect.getMetadata(IPC_GATEWAY_KEY, proto, methodName)
      const channel = Reflect.getMetadata(IPC_METHOD_KEY, proto, methodName)
      const type = Reflect.getMetadata(IPC_TYPE_KEY, proto, methodName)

      if (!channel || !type) return

      // --- 处理 INVOKE 和 SEND (渲染进程 -> 主进程) ---
      if (type === IPCType.INVOKE || type === IPCType.SEND) {
        if (!this.gatewayHandlers.has(gateway)) {
          this.gatewayHandlers.set(gateway, new Map())
          logger.info(`[IPC] 注册网关: ${gateway}`)
        }
        this.gatewayHandlers.get(gateway)!.set(channel, controller[methodName].bind(controller))
      }
      // --- 处理 ON 和 ONCE (主进程 -> 渲染进程) ---
      else if (type === IPCType.ON || type === IPCType.ONCE) {
        /**
         * 这种情况下，Controller 里的方法其实是一个“发送动作”。
         * 我们重新定义该方法，使其调用 webContents.send
         */
        controller[methodName] = (webContents: Electron.WebContents, ...args: any[]) => {
          if (!webContents || webContents.isDestroyed()) {
            logger.warn(`[IPC] 尝试向已销毁的 WebContents 发送消息: ${channel}`)
            return
          }
          // 主进程主动推送到渲染进程，这里通常不走网关，直接走原始 channel 效率最高
          webContents.send(channel, ...args)
        }
        this.senders.add(channel)
      }

      logger.info(`[IPC] 注册通道: ${channel} [${type}]`)
    })
  }

  /**
   * 真正开启物理网关监听
   */
  public static bootstrap(): void {
    // 启动物理网关逻辑 (仅针对双向通信)
    for (const [gatewayName, handlers] of this.gatewayHandlers) {
      ipcMain.handle(gatewayName, async (event, payload: { channel: string; args: any[] }) => {
        //logger.info(`[IPC] 网关处理: ${gatewayName} ${payload.channel}`)
        const { channel, args } = payload
        const handler = handlers.get(channel)
        if (!handler) throw new Error(`Logic channel ${channel} not found in ${gatewayName}`)
        return await handler(event, ...args)
      })

      ipcMain.on(gatewayName, (event, payload) => {
        //logger.info(`[IPC] 网关处理: ${gatewayName} ${payload.channel}`)
        const { channel, args } = payload
        const handler = handlers.get(channel)
        if (handler) {
          // 执行异步函数但不等待返回（符合 send 的语义）
          handler(event, ...args)
        }
      })
    }
  }
}
