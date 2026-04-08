export type EmbedNetworkLogLevel = 'info' | 'error'

export interface EmbedNetworkLogEntry {
  id: string
  time: string
  level: EmbedNetworkLogLevel
  message: string
  payload: Record<string, any>
}

const NETWORK_LOG_EVENT = 'embed-network-log'

let sequence = 0

const nowTime = (): string => {
  return new Date().toLocaleTimeString('zh-CN', { hour12: false })
}

export const emitNetworkLog = (level: EmbedNetworkLogLevel, message: string, payload: Record<string, any>): void => {
  if (typeof window === 'undefined') return

  const entry: EmbedNetworkLogEntry = {
    id: `${Date.now()}-${++sequence}`,
    time: nowTime(),
    level,
    message,
    payload
  }

  window.dispatchEvent(
    new CustomEvent<EmbedNetworkLogEntry>(NETWORK_LOG_EVENT, {
      detail: entry
    })
  )
}

export const subscribeNetworkLog = (callback: (entry: EmbedNetworkLogEntry) => void): (() => void) => {
  const listener = (event: Event): void => {
    const customEvent = event as CustomEvent<EmbedNetworkLogEntry>
    if (customEvent.detail) {
      callback(customEvent.detail)
    }
  }

  window.addEventListener(NETWORK_LOG_EVENT, listener as EventListener)
  return () => window.removeEventListener(NETWORK_LOG_EVENT, listener as EventListener)
}
