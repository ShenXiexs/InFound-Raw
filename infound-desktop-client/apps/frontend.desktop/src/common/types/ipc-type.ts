import { AppState, LoggerLevel, WebSocketMessage } from '@infound/desktop-shared'
import { TkShopSetting } from '@common/types/tk-type'

export const IPC_CHANNELS = {
  APP_LOGGER: 'app-logger',
  APP_MINIMIZED: 'app-minimized',
  APP_MAXIMIZED: 'app-maximized',
  APP_CLOSED: 'app-closed',
  APP_GET_WINDOW_ID: 'app-get-window-id',
  APP_AUTH_LOGIN: 'app-auth-login',
  APP_AUTH_LOGOUT: 'app-auth-logout',
  APP_AUTH_GET_CURRENT_USER: 'app-auth-get-current-user',
  APP_AUTH_CHECK_TOKEN: 'app-auth-check-token',

  APP_GLOBAL_STATE_GET_ALL: 'app-global-state-get-all',
  APP_GLOBAL_STATE_SET_ITEM: 'app-global-state-set-item',

  APP_OPEN_WINDOW_DEV_TOOLS: 'app-open-window-dev-tools',
  APP_OPEN_SUB_WINDOW_DEV_TOOLS: 'app-open-sub-window-dev-tools',
  APP_OPEN_EXTERNAL_LINK: 'app-open-external-link',

  RENDERER_MONITOR_APP_GLOBAL_STATE_SYNC: 'renderer-monitor-app-global-state-sync',
  RENDERER_MONITOR_APP_SPLASH_WINDOW_STATE_SYNC: 'renderer-monitor-app-splash-window-state-sync',
  RENDERER_MONITOR_TK_SHOP_ALL_TAB_ITEM_SETTINGS_SYNC: 'renderer-monitor-tk-shop-all-tab-item-settings-sync',
  RENDERER_MONITOR_WEBSOCKET_RECEIVE: 'renderer-monitor-websocket-receive',

  TK_SHOP_OPEN_WINDOW: 'tk-shop-open-window',
  TK_SHOP_GET_TKSHOP_SETTING: 'tk-shop-get-tk-shop-setting',

  RPA_SELLER_LOGIN: 'rpa-seller-login',
  RPA_SELLER_OUT_REACH: 'rpa-seller-out-reach'
} as const

export type IPCChannelKey = (typeof IPC_CHANNELS)[keyof typeof IPC_CHANNELS]

export interface AppProtocol {
  [IPC_CHANNELS.APP_LOGGER]: { params: [LoggerLevel, string, ...any[]]; return: void }
  [IPC_CHANNELS.APP_MINIMIZED]: { params: [number]; return: void }
  [IPC_CHANNELS.APP_MAXIMIZED]: { params: [number]; return: { success: boolean; isMaximized: boolean; error?: string } }
  [IPC_CHANNELS.APP_CLOSED]: { params: [number]; return: void }
  [IPC_CHANNELS.APP_GET_WINDOW_ID]: { params: []; return: number }
  [IPC_CHANNELS.APP_AUTH_LOGIN]: {
    params: [string, string]
    return: { success: boolean; error?: string }
  }
  [IPC_CHANNELS.APP_AUTH_LOGOUT]: {
    params: []
    return: { success: boolean; error?: string }
  }
  [IPC_CHANNELS.APP_AUTH_GET_CURRENT_USER]: {
    params: []
    return: { success: boolean; data?: Record<string, any>; error?: string }
  }
  [IPC_CHANNELS.APP_AUTH_CHECK_TOKEN]: {
    params: []
    return: { success: boolean; data?: Record<string, any>; error?: string }
  }

  [IPC_CHANNELS.APP_GLOBAL_STATE_GET_ALL]: { params: []; return: { success: boolean; data: AppState } }
  [IPC_CHANNELS.APP_GLOBAL_STATE_SET_ITEM]: { params: [{ path: string; value: any }]; return: { success: boolean } }

  [IPC_CHANNELS.APP_OPEN_WINDOW_DEV_TOOLS]: { params: [number, 'left' | 'right' | 'bottom' | 'undocked' | 'detach']; return: void }
  [IPC_CHANNELS.APP_OPEN_SUB_WINDOW_DEV_TOOLS]: { params: [number, 'left' | 'right' | 'bottom' | 'undocked' | 'detach']; return: void }
  [IPC_CHANNELS.APP_OPEN_EXTERNAL_LINK]: { params: [string]; return: void }

  [IPC_CHANNELS.RENDERER_MONITOR_APP_GLOBAL_STATE_SYNC]: { params: [{ path: string; value: any }]; return: void }
  [IPC_CHANNELS.RENDERER_MONITOR_APP_SPLASH_WINDOW_STATE_SYNC]: { params: [{ percent: number; status: string }]; return: void }
  [IPC_CHANNELS.RENDERER_MONITOR_WEBSOCKET_RECEIVE]: { params: [WebSocketMessage]; return: void }

  [IPC_CHANNELS.TK_SHOP_OPEN_WINDOW]: { params: [string]; return: void }
  [IPC_CHANNELS.TK_SHOP_GET_TKSHOP_SETTING]: { params: [number]; return: { success: boolean; data: TkShopSetting } }

  [IPC_CHANNELS.RPA_SELLER_LOGIN]: { params: []; return: void }
  [IPC_CHANNELS.RPA_SELLER_OUT_REACH]: { params: []; return: boolean }
}

export interface IPCAPI {
  getCurrentBrowserWindowId(): Promise<number>

  invoke<K extends keyof AppProtocol>(channel: K, ...args: AppProtocol[K]['params']): Promise<AppProtocol[K]['return']>

  send<K extends keyof AppProtocol>(channel: K, ...args: AppProtocol[K]['params']): void

  on<K extends keyof AppProtocol>(channel: K, callback: (...args: AppProtocol[K]['params']) => void): () => void

  once<K extends keyof AppProtocol>(channel: K, callback: (...args: AppProtocol[K]['params']) => void): void
}
