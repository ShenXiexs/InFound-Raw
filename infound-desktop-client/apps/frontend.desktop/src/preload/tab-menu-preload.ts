import { contextBridge, ipcRenderer } from 'electron'

contextBridge.exposeInMainWorld('ipc', {
  send: (channel: string, ...args: any[]) => ipcRenderer.send(channel, ...args),
  on: (channel: string, listener: (...args: any[]) => void) => ipcRenderer.on(channel, listener),
  invoke: (channel: string, ...args: any[]) => ipcRenderer.invoke(channel, ...args)
})
