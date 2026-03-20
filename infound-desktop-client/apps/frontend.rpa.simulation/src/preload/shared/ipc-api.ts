import { ipcRenderer } from 'electron'
import { AppProtocol, IPCAPI } from '@common/types/ipc-type'

const ipcAPI: IPCAPI = {
  invoke: async (channel, ...args) => {
    // 这里的 channel 和 args 会自动根据 IIpcApi 提示类型
    return await ipcRenderer.invoke(channel, ...args)
  },
  send: (channel, ...args) => {
    ipcRenderer.send(channel, ...args)
  },
  on: <K extends keyof AppProtocol>(channel: K, callback: (...args: AppProtocol[K]['params']) => void) => {
    const subscription = (_event: any, ...args: AppProtocol[K]['params']): void => callback(...args)
    ipcRenderer.on(channel, subscription)
    return () => ipcRenderer.removeListener(channel, subscription)
  },
  once: <K extends keyof AppProtocol>(channel: K, callback: (...args: AppProtocol[K]['params']) => void) => {
    ipcRenderer.once(channel, (_event, ...args: AppProtocol[K]['params']) => callback(...args))
  }
}
export { ipcAPI }
