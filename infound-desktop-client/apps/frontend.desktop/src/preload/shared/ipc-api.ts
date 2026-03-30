import { ipcRenderer } from 'electron'
import { AppProtocol, IPC_CHANNELS, IPCAPI } from '@common/types/ipc-type'
import { IPCGateway } from '../../main/modules/ipc/base/ipc-decorator'

/**
 * 辅助函数：根据逻辑通道找到对应的物理网关
 * 这里你可以维护一个映射表，或者简单地根据通道前缀判断
 */
function getGatewayByChannel(channel: string): string {
  if (channel.startsWith('app-')) {
    return IPCGateway.APP
  } else if (channel.startsWith('websocket-')) {
    return IPCGateway.WS
  } else if (channel.startsWith('tk-')) {
    return IPCGateway.TK
  } else if (channel.startsWith('tabs-')) {
    return IPCGateway.TAB
  } else if (channel.startsWith('rpa-')) {
    return IPCGateway.RPA
  } else if (channel.startsWith('renderer-monitor-')) {
    return IPCGateway.MONITOR
  }
  return IPCGateway.APP // 默认走 APP 网关
}

const ipcAPI: IPCAPI = {
  invoke: async (channel, ...args) => {
    const gateway = getGatewayByChannel(channel)
    //loggerAPI.info(`[IPC] 发送请求: ${gateway} ${channel}`)
    return await ipcRenderer.invoke(gateway, { channel, args })
  },
  send: (channel, ...args) => {
    const gateway = getGatewayByChannel(channel)
    //loggerAPI.info(`[IPC] 发送请求: ${gateway} ${channel}`)
    ipcRenderer.send(gateway, { channel, args })
  },
  on: <K extends keyof AppProtocol>(channel: K, callback: (...args: AppProtocol[K]['params']) => void) => {
    const subscription = (_event: any, ...args: AppProtocol[K]['params']): void => callback(...args)
    ipcRenderer.on(channel, subscription)
    return () => ipcRenderer.removeListener(channel, subscription)
  },
  once: <K extends keyof AppProtocol>(channel: K, callback: (...args: AppProtocol[K]['params']) => void) => {
    ipcRenderer.once(channel, (_event, ...args: AppProtocol[K]['params']) => callback(...args))
  },
  getCurrentBrowserWindowId: async (): Promise<number> => {
    return await ipcRenderer.invoke(IPCGateway.APP, { channel: IPC_CHANNELS.APP_GET_WINDOW_ID, args: [] })
  }
}

export { ipcAPI }
