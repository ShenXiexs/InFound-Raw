interface ImportMetaEnv {
  readonly VITE_LOG_LEVEL: string
  readonly VITE_LOG_ENABLE: string
  readonly VITE_APP_NAME: string
  readonly VITE_SELLER_RPA_WS_ENABLED?: string
  readonly VITE_SELLER_RPA_WS_BASE_URL?: string
  readonly VITE_SELLER_RPA_WS_AUTH_HEADER?: string
  readonly VITE_SELLER_RPA_WS_TOKEN?: string
  readonly VITE_SELLER_RPA_WS_USER_ID?: string
  readonly VITE_SELLER_RPA_WS_INBOX_DESTINATION?: string
  readonly VITE_SELLER_RPA_WS_RECONNECT_DELAY_MS?: string
  readonly VITE_SELLER_RPA_WS_HEARTBEAT_INCOMING_MS?: string
  readonly VITE_SELLER_RPA_WS_HEARTBEAT_OUTGOING_MS?: string
  readonly VITE_SELLER_RPA_API_BASE_URL?: string
  readonly VITE_SELLER_RPA_API_AUTH_HEADER?: string
  readonly VITE_SELLER_RPA_API_TOKEN?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
