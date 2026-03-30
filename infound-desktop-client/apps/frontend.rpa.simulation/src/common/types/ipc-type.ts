import { LoggerLevel } from '@infound/desktop-electron'
import {
  OutreachFilterConfigInput,
  PlaywrightSimulationPayloadInput,
  SampleManagementPayloadInput,
  SellerChatbotPayloadInput,
  SellerCreatorDetailPayloadInput
} from '@desktop-rpa'

export const IPC_CHANNELS = {
  APP_LOGGER: 'app-logger',
  APP_MINIMIZED: 'app-minimized',
  APP_MAXIMIZED: 'app-maximized',
  APP_CLOSED: 'app-closed',
  APP_OPEN_WINDOW_DEV_TOOLS: 'app-open-window-dev-tools',
  APP_OPEN_SUB_WINDOW_DEV_TOOLS: 'app-open-sub-window-dev-tools',

  RPA_SELLER_LOGIN: 'rpa-seller-login',
  RPA_SELLER_OUT_REACH: 'rpa-seller-out-reach',
  RPA_SELLER_CHATBOT: 'rpa-seller-chatbot',
  RPA_SELLER_CREATOR_DETAIL: 'rpa-seller-creator-detail',
  RPA_SAMPLE_MANAGEMENT: 'rpa-sample-management',
  RPA_EXECUTE_SIMULATION: 'rpa-execute-simulation'
} as const

export type IPCChannelKey = (typeof IPC_CHANNELS)[keyof typeof IPC_CHANNELS]

export interface AppProtocol {
  [IPC_CHANNELS.APP_LOGGER]: { params: [LoggerLevel, string, ...any[]]; return: void }
  [IPC_CHANNELS.APP_MINIMIZED]: { params: []; return: void }
  [IPC_CHANNELS.APP_MAXIMIZED]: { params: []; return: { success: boolean; isMaximized: boolean; error?: string } }
  [IPC_CHANNELS.APP_CLOSED]: { params: []; return: void }
  [IPC_CHANNELS.APP_OPEN_WINDOW_DEV_TOOLS]: { params: ['left' | 'right' | 'bottom' | 'undocked' | 'detach']; return: void }
  [IPC_CHANNELS.APP_OPEN_SUB_WINDOW_DEV_TOOLS]: { params: ['left' | 'right' | 'bottom' | 'undocked' | 'detach']; return: void }

  [IPC_CHANNELS.RPA_SELLER_LOGIN]: { params: []; return: void }
  [IPC_CHANNELS.RPA_SELLER_OUT_REACH]: { params: [OutreachFilterConfigInput?]; return: void }
  [IPC_CHANNELS.RPA_SELLER_CHATBOT]: { params: [SellerChatbotPayloadInput]; return: void }
  [IPC_CHANNELS.RPA_SELLER_CREATOR_DETAIL]: { params: [SellerCreatorDetailPayloadInput]; return: void }
  [IPC_CHANNELS.RPA_SAMPLE_MANAGEMENT]: { params: [SampleManagementPayloadInput?]; return: void }
  [IPC_CHANNELS.RPA_EXECUTE_SIMULATION]: { params: [PlaywrightSimulationPayloadInput?]; return: void }
}

export interface IPCAPI {
  invoke<K extends keyof AppProtocol>(channel: K, ...args: AppProtocol[K]['params']): Promise<AppProtocol[K]['return']>

  send<K extends keyof AppProtocol>(channel: K, ...args: AppProtocol[K]['params']): void

  on<K extends keyof AppProtocol>(channel: K, callback: (...args: AppProtocol[K]['params']) => void): () => void

  once<K extends keyof AppProtocol>(channel: K, callback: (...args: AppProtocol[K]['params']) => void): void
}
