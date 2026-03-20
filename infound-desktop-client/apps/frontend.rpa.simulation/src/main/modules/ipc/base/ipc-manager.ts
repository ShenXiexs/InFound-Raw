// main/ipc/IPCManager.ts
import { ipcMain } from 'electron'
import { IPC_METHOD_KEY, IPC_TYPE_KEY, IPCType } from './ipc-decorator'
import { logger } from '../../../utils/logger'

export class IPCManager {
  private static registeredChannels = new Set<string>()

  public static register(controller: any): void {
    const proto = Object.getPrototypeOf(controller)
    Object.getOwnPropertyNames(proto).forEach((methodName) => {
      const channel = Reflect.getMetadata(IPC_METHOD_KEY, proto, methodName)
      const type = Reflect.getMetadata(IPC_TYPE_KEY, proto, methodName)

      if (!channel || !type) return

      if (this.registeredChannels.has(channel)) {
        logger.warn(`[IPC] 通道 ${channel} 已注册，跳过重复操作。`)
        return
      }

      switch (type) {
        case IPCType.INVOKE:
          // 渲染进程 invoke -> 主进程 handle
          ipcMain.handle(channel, async (...args) => {
            try {
              return await controller[methodName](...args)
            } catch (error) {
              logger.error(`[IPC] invoke 通道执行失败: channel=${channel} error=${(error as Error)?.message || error}`)
              throw error
            }
          })
          break

        case IPCType.SEND:
          // 渲染进程 send -> 主进程 on
          ipcMain.on(channel, (...args) => {
            Promise.resolve(controller[methodName](...args)).catch((error) => {
              logger.error(`[IPC] send 通道执行失败: channel=${channel} error=${(error as Error)?.message || error}`)
            })
          })
          break

        case IPCType.ON:
        case IPCType.ONCE:
          // 这些类型是主进程向渲染进程发消息，不需要 ipcMain.handle 或 ipcMain.on
          // 这里我们可以在 Controller 中提供一个辅助方法
          controller[methodName] = (webContents: Electron.WebContents, ...args: any[]) => {
            if (type === IPCType.ON) {
              webContents.send(channel, ...args)
            } else {
              // 这里的 once 由渲染进程自己处理，主进程发送即可
              webContents.send(channel, ...args)
            }
          }
          break
      }

      this.registeredChannels.add(channel)
      logger.info(`[IPC] 成功注册通道: ${channel} ${type}`)
    })
  }
}
