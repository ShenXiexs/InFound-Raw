import type { AppState } from '@infound/desktop-base'
import type { LoggerLevel } from '@infound/desktop-electron/types'

export const IPC_CHANNELS = {
  APP_LOGGER: 'app-logger',
  APP_GET_WINDOW_ID: 'app-get-window-id',

  APP_GLOBAL_STATE_GET_ALL: 'app-global-state-get-all',
  APP_GLOBAL_STATE_SET_ITEM: 'app-global-state-set-item',

  RENDERER_MONITOR_APP_GLOBAL_STATE_SYNC: 'renderer-monitor-app-global-state-sync'
}

export interface AppProtocol {
  [IPC_CHANNELS.APP_LOGGER]: { params: [LoggerLevel, string, ...any[]]; return: void }
  [IPC_CHANNELS.APP_GET_WINDOW_ID]: { params: []; return: number }

  [IPC_CHANNELS.APP_GLOBAL_STATE_GET_ALL]: { params: []; return: { success: boolean; data: AppState } }
  [IPC_CHANNELS.APP_GLOBAL_STATE_SET_ITEM]: { params: [{ path: string; value: any }]; return: { success: boolean } }

  [IPC_CHANNELS.RENDERER_MONITOR_APP_GLOBAL_STATE_SYNC]: { params: [{ path: string; value: any }]; return: void }
}

export interface IPCAPI {
  getCurrentBrowserWindowId(): Promise<number>

  invoke<K extends keyof AppProtocol>(channel: K, ...args: AppProtocol[K]['params']): Promise<AppProtocol[K]['return']>

  send<K extends keyof AppProtocol>(channel: K, ...args: AppProtocol[K]['params']): void

  sendDirect<K extends keyof AppProtocol>(channel: K, ...args: AppProtocol[K]['params']): void

  on<K extends keyof AppProtocol>(channel: K, callback: (...args: AppProtocol[K]['params']) => void): () => void

  once<K extends keyof AppProtocol>(channel: K, callback: (...args: AppProtocol[K]['params']) => void): void
}
