import { AppState } from '@infound/desktop-base'
import { LoggerLevel } from '@infound/desktop-electron'
import { TkShopSetting } from '@common/types/tk-type'
import { Tab } from '@common/types/tab-type'

export const IPC_CHANNELS = {
  APP_LOGGER: 'app-logger',
  APP_MINIMIZED: 'app-minimized',
  APP_MAXIMIZED: 'app-maximized',
  APP_CLOSED: 'app-closed',
  APP_GET_WINDOW_ID: 'app-get-window-id',

  APP_GLOBAL_STATE_GET_ALL: 'app-global-state-get-all',
  APP_GLOBAL_STATE_SET_ITEM: 'app-global-state-set-item',

  APP_OPEN_WINDOW_DEV_TOOLS: 'app-open-window-dev-tools',
  APP_OPEN_SUB_WINDOW_DEV_TOOLS: 'app-open-sub-window-dev-tools',
  APP_OPEN_EXTERNAL_LINK: 'app-open-external-link',

  API_AUTH_LOGIN: 'api-auth-login',
  API_AUTH_LOGOUT: 'api-auth-logout',
  API_AUTH_GET_CURRENT_USER: 'api-auth-get-current-user',
  API_AUTH_CHECK_TOKEN: 'api-auth-check-token',

  WEBSOCKET_CONNECT: 'websocket-connect',
  WEBSOCKET_DISCONNECT: 'websocket-disconnect',

  TK_SHOP_OPEN_WINDOW: 'tk-shop-open-window',
  TK_SHOP_GET_TKSHOP_SETTING: 'tk-shop-get-tk-shop-setting',
  TK_SHOP_GET_ENTRIES: 'tk-shop-get-entries',
  TK_SHOP_ADD: 'tk-shop-add',
  TK_SHOP_LIST: 'tk-shop-list',
  TK_SHOP_UPDATE: 'tk-shop-update',
  TK_SHOP_DELETE: 'tk-shop-delete',

  TABS_ACTIVATE_ITEM: 'tabs-activate-item',
  TABS_CLOSE_ITEM: 'tabs-close-item',
  TABS_NAVIGATE_BACK: 'tabs-navigate-back',
  TABS_NAVIGATE_FORWARD: 'tabs-navigate-forward',
  TABS_NAVIGATE_RELOAD: 'tabs-navigate-reload',
  TABS_SHOW_ITEMS_MENU: 'tabs-show-items-menu',
  TABS_REORDER_ITEMS: 'tabs-reorder-items',

  RPA_SELLER_LOGIN: 'rpa-seller-login',
  RPA_SELLER_OUT_REACH: 'rpa-seller-out-reach',
  RPA_TASK_START: 'rpa-task-start',

  RENDERER_MONITOR_APP_GLOBAL_STATE_SYNC: 'renderer-monitor-app-global-state-sync',
  RENDERER_MONITOR_APP_SPLASH_WINDOW_STATE_SYNC: 'renderer-monitor-app-splash-window-state-sync',
  RENDERER_MONITOR_TK_SHOP_ALL_TAB_ITEM_SETTINGS_SYNC: 'renderer-monitor-tk-shop-all-tab-item-settings-sync',
  RENDERER_MONITOR_TABS_UPDATED: 'renderer-monitor-tabs-updated',
  RENDERER_MONITOR_TABS_NAVIGATION_STATE: 'renderer-monitor-tabs-navigation-state'
} as const

export type IPCChannelKey = (typeof IPC_CHANNELS)[keyof typeof IPC_CHANNELS]

export interface ShopEntryInfoDTO {
  entryId?: number
  regionCode: string
  regionName: string
  shopType: 'LOCAL' | 'CROSS_BORDER'
  loginUrl: string
}

export interface ShopListInfoDTO {
  id: string
  name: string
  entryId?: number
  remark?: string
  shopLastOpen?: string
  regionCode: string
  regionName: string
  shopType: 'LOCAL' | 'CROSS_BORDER'
  loginUrl: string
}

export interface TkShopOpenWindowPayload {
  id: string
  name: string
  region: string
  loginUrl: string
}

export interface AppProtocol {
  [IPC_CHANNELS.APP_LOGGER]: { params: [LoggerLevel, string, ...any[]]; return: void }
  [IPC_CHANNELS.APP_MINIMIZED]: { params: [number]; return: void }
  [IPC_CHANNELS.APP_MAXIMIZED]: { params: [number]; return: { success: boolean; isMaximized: boolean; error?: string } }
  [IPC_CHANNELS.APP_CLOSED]: { params: [number]; return: void }
  [IPC_CHANNELS.APP_GET_WINDOW_ID]: { params: []; return: number }

  [IPC_CHANNELS.APP_GLOBAL_STATE_GET_ALL]: { params: []; return: { success: boolean; data: AppState } }
  [IPC_CHANNELS.APP_GLOBAL_STATE_SET_ITEM]: { params: [{ path: string; value: any }]; return: { success: boolean } }

  [IPC_CHANNELS.APP_OPEN_WINDOW_DEV_TOOLS]: { params: [number, 'left' | 'right' | 'bottom' | 'undocked' | 'detach']; return: void }
  [IPC_CHANNELS.APP_OPEN_SUB_WINDOW_DEV_TOOLS]: { params: [number, 'left' | 'right' | 'bottom' | 'undocked' | 'detach']; return: void }
  [IPC_CHANNELS.APP_OPEN_EXTERNAL_LINK]: { params: [string]; return: void }

  [IPC_CHANNELS.API_AUTH_LOGIN]: {
    params: [string, string]
    return: { success: boolean; error?: string }
  }
  [IPC_CHANNELS.API_AUTH_LOGOUT]: {
    params: []
    return: { success: boolean; error?: string }
  }
  [IPC_CHANNELS.API_AUTH_GET_CURRENT_USER]: {
    params: []
    return: { success: boolean; data?: Record<string, any>; error?: string }
  }
  [IPC_CHANNELS.API_AUTH_CHECK_TOKEN]: {
    params: []
    return: { success: boolean; code?: number; data?: Record<string, any>; error?: string }
  }

  [IPC_CHANNELS.WEBSOCKET_CONNECT]: { params: []; return: void }
  [IPC_CHANNELS.WEBSOCKET_DISCONNECT]: { params: []; return: void }

  [IPC_CHANNELS.TK_SHOP_OPEN_WINDOW]: { params: [TkShopOpenWindowPayload]; return: void }
  [IPC_CHANNELS.TK_SHOP_GET_TKSHOP_SETTING]: { params: [number]; return: { success: boolean; data: TkShopSetting } }
  [IPC_CHANNELS.TK_SHOP_GET_ENTRIES]: { params: []; return: { success: boolean; data?: ShopEntryInfoDTO[]; error?: string } }
  [IPC_CHANNELS.TK_SHOP_ADD]: {
    params: [{ name: string; entryId: number; remark?: string }]
    return: { success: boolean; data?: Record<string, any>; error?: string }
  }
  [IPC_CHANNELS.TK_SHOP_LIST]: { params: []; return: { success: boolean; data?: ShopListInfoDTO[]; error?: string } }
  [IPC_CHANNELS.TK_SHOP_UPDATE]: {
    params: [{ id: string; name: string; entryId: number; remark?: string }]
    return: { success: boolean; data?: Record<string, any>; error?: string }
  }
  [IPC_CHANNELS.TK_SHOP_DELETE]: {
    params: [{ id: string }]
    return: { success: boolean; data?: Record<string, any>; error?: string }
  }

  [IPC_CHANNELS.RPA_SELLER_LOGIN]: { params: []; return: void }
  [IPC_CHANNELS.RPA_SELLER_OUT_REACH]: { params: []; return: boolean }
  [IPC_CHANNELS.RPA_TASK_START]: { params: []; return: void }

  [IPC_CHANNELS.TABS_ACTIVATE_ITEM]: { params: [id: string]; return: void }
  [IPC_CHANNELS.TABS_CLOSE_ITEM]: { params: [id: string]; return: void }
  [IPC_CHANNELS.TABS_NAVIGATE_BACK]: { params: []; return: void }
  [IPC_CHANNELS.TABS_NAVIGATE_FORWARD]: { params: []; return: void }
  [IPC_CHANNELS.TABS_NAVIGATE_RELOAD]: { params: []; return: void }
  [IPC_CHANNELS.TABS_SHOW_ITEMS_MENU]: { params: [x: number, y: number]; return: void }
  [IPC_CHANNELS.TABS_REORDER_ITEMS]: { params: [orderedIds: string[]]; return: void }

  [IPC_CHANNELS.RENDERER_MONITOR_APP_GLOBAL_STATE_SYNC]: { params: [{ path: string; value: any }]; return: void }
  [IPC_CHANNELS.RENDERER_MONITOR_APP_SPLASH_WINDOW_STATE_SYNC]: { params: [{ percent: number; status: string }]; return: void }
  [IPC_CHANNELS.RENDERER_MONITOR_TABS_UPDATED]: { params: [{ activeId: string; tabs: Tab[] }]; return: void }
  [IPC_CHANNELS.RENDERER_MONITOR_TABS_NAVIGATION_STATE]: {
    params: [{ canGoBack: boolean; canGoForward: boolean }]
    return: void
  }
}

export interface IPCAPI {
  getCurrentBrowserWindowId(): Promise<number>

  invoke<K extends keyof AppProtocol>(channel: K, ...args: AppProtocol[K]['params']): Promise<AppProtocol[K]['return']>

  send<K extends keyof AppProtocol>(channel: K, ...args: AppProtocol[K]['params']): void

  on<K extends keyof AppProtocol>(channel: K, callback: (...args: AppProtocol[K]['params']) => void): () => void

  once<K extends keyof AppProtocol>(channel: K, callback: (...args: AppProtocol[K]['params']) => void): void
}
