import { AppReleaseInfo, AppState } from '@infound/desktop-base'
import { LoggerLevel } from '@infound/desktop-electron'
import { TkShopOpenWindowPayload, TkShopSetting } from '@common/types/tk-type'
import { Tab } from '@common/types/tab-type'

export enum IPCGateway {
  APP = 'gateway:app',
  MONITOR = 'gateway:monitor',
  TK = 'gateway:tk',
  TAB = 'gateway:tab',
  RPA = 'gateway:rpa',
  API = 'gateway:api',
  WS = 'gateway:ws'
}

export enum IPCType {
  INVOKE = 'invoke', // 渲染进程通过 invoke 调用主进程 (双向)
  ON = 'on', // 渲染进程通过 on 持续监听主进程 (由主进程发送)
  SEND = 'send', // 渲染进程通过 send 发送消息，主进程不需要返回值 (单向)
  ONCE = 'once' // 渲染进程只监听一次，由主进程发送
}

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
  /** 模态 BrowserWindow 打开独立部署的 embed 页（如设置），挂靠在调用方窗口下 */
  APP_OPEN_EMBED_MODAL: 'app-open-embed-modal',
  /** 关闭由 APP_OPEN_EMBED_MODAL 打开的模态 embed 窗口（由 embed 页内「关闭」调用） */
  APP_CLOSE_EMBED_MODAL: 'app-close-embed-modal',

  APP_UPDATE_INFO: 'app-update-info',
  APP_UPDATE_CHECK: 'app-update-check',
  APP_UPDATE_DOWNLOAD: 'app-update-download',
  APP_UPDATE_CLOSE: 'app-update-close',

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
  TABS_OPEN_OUTREACH: 'tabs-open-outreach',
  TABS_OPEN_FULFILLMENT: 'tabs-open-fulfillment',
  /** 在 embed 标签中打开指定 hash 路径，如 `/settings?tab=profile`；主窗口调用时会落到已打开的店铺窗口 */
  TABS_OPEN_EMBED: 'tabs-open-embed',
  TABS_SHOW_ITEMS_MENU: 'tabs-show-items-menu',
  TABS_REORDER_ITEMS: 'tabs-reorder-items',

  TABS_CREATE_TAB_MENU: 'tabs-create-tab-menu',
  TABS_MENU_SWITCH_TAB: 'tabs-menu-switch-tab',
  TABS_MENU_CLOSE_TAB: 'tabs-menu-close-tab',
  TABS_REORDER_FROM_MENU: 'tabs-reorder-from-menu',

  RPA_SELLER_LOGIN: 'rpa-seller-login',
  RPA_SELLER_OUT_REACH: 'rpa-seller-out-reach',
  RPA_TASK_START: 'rpa-task-start',

  RENDERER_MONITOR_APP_GLOBAL_STATE_SYNC: 'renderer-monitor-app-global-state-sync',
  RENDERER_MONITOR_APP_SPLASH_WINDOW_STATE_SYNC: 'renderer-monitor-app-splash-window-state-sync',
  RENDERER_MONITOR_APP_UPDATE_PROGRESS: 'renderer-monitor-app-update-progress',
  RENDERER_MONITOR_TK_SHOP_ALL_TAB_ITEM_SETTINGS_SYNC: 'renderer-monitor-tk-shop-all-tab-item-settings-sync',
  RENDERER_MONITOR_TABS_UPDATED: 'renderer-monitor-tabs-updated',
  RENDERER_MONITOR_TABS_NAVIGATION_STATE: 'renderer-monitor-tabs-navigation-state'
  //RENDERER_MONITOR_TABS_MENU_INIT: 'renderer-monitor-tabs-menu-init'
} as const

export type IPCChannelKey = (typeof IPC_CHANNELS)[keyof typeof IPC_CHANNELS]

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
  [IPC_CHANNELS.APP_OPEN_EMBED_MODAL]: { params: [hashPath: string]; return: { success: boolean; error?: string } }
  [IPC_CHANNELS.APP_CLOSE_EMBED_MODAL]: { params: []; return: { success: boolean } }

  [IPC_CHANNELS.APP_UPDATE_INFO]: { params: []; return: { success: boolean; data?: AppReleaseInfo; error?: string } }
  [IPC_CHANNELS.APP_UPDATE_CHECK]: { params: []; return: { success: boolean; data?: AppReleaseInfo; error?: string } }
  [IPC_CHANNELS.APP_UPDATE_DOWNLOAD]: { params: [number, 'immediately' | 'afterExit']; return: { success: boolean; error?: string } }
  [IPC_CHANNELS.APP_UPDATE_CLOSE]: { params: []; return: void }

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
  [IPC_CHANNELS.TK_SHOP_GET_ENTRIES]: {
    params: []
    return: {
      success: boolean
      data?: {
        entryId?: number
        regionCode: string
        regionName: string
        shopType: 'LOCAL' | 'CROSS_BORDER'
        loginUrl: string
        homeUrl: string
      }[]
      error?: string
    }
  }
  [IPC_CHANNELS.TK_SHOP_ADD]: {
    params: [{ name: string; entryId: number; remark?: string }]
    return: { success: boolean; data?: Record<string, any>; error?: string }
  }
  [IPC_CHANNELS.TK_SHOP_LIST]: {
    params: []
    return: {
      success: boolean
      data?: {
        id: string
        name: string
        entryId?: number
        remark?: string
        shopLastOpen?: string
        regionCode: string
        regionName: string
        shopType: 'LOCAL' | 'CROSS_BORDER'
        loginUrl: string
        homeUrl: string
      }[]
      error?: string
    }
  }
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
  [IPC_CHANNELS.TABS_OPEN_OUTREACH]: { params: []; return: { success: boolean; error?: string } }
  [IPC_CHANNELS.TABS_OPEN_FULFILLMENT]: { params: []; return: { success: boolean; error?: string } }
  [IPC_CHANNELS.TABS_OPEN_EMBED]: { params: [hashPath: string]; return: { success: boolean; error?: string } }
  [IPC_CHANNELS.TABS_SHOW_ITEMS_MENU]: { params: [x: number, y: number]; return: void }
  [IPC_CHANNELS.TABS_REORDER_ITEMS]: { params: [orderedIds: string[]]; return: void }

  [IPC_CHANNELS.TABS_CREATE_TAB_MENU]: { params: [x: number, y: number]; return: void }
  [IPC_CHANNELS.TABS_MENU_SWITCH_TAB]: { params: [tabId: string]; return: void }
  [IPC_CHANNELS.TABS_MENU_CLOSE_TAB]: { params: [tabId: string]; return: void }
  [IPC_CHANNELS.TABS_REORDER_FROM_MENU]: { params: [orderedIds: string[]]; return: void }

  [IPC_CHANNELS.RENDERER_MONITOR_APP_GLOBAL_STATE_SYNC]: { params: [{ path: string; value: any }]; return: void }
  [IPC_CHANNELS.RENDERER_MONITOR_APP_SPLASH_WINDOW_STATE_SYNC]: { params: [{ percent: number; status: string }]; return: void }
  [IPC_CHANNELS.RENDERER_MONITOR_APP_UPDATE_PROGRESS]: { params: [speed: string, percent: number]; return: void }
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

  sendDirect<K extends keyof AppProtocol>(channel: K, ...args: AppProtocol[K]['params']): void

  on<K extends keyof AppProtocol>(channel: K, callback: (...args: AppProtocol[K]['params']) => void): () => void

  once<K extends keyof AppProtocol>(channel: K, callback: (...args: AppProtocol[K]['params']) => void): void
}
