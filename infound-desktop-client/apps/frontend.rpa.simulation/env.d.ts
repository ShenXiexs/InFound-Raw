interface ImportMetaEnv {
  readonly VITE_LOG_LEVEL: string
  readonly VITE_LOG_ENABLE: string
  readonly VITE_APP_NAME: string
  readonly VITE_SELLER_RPA_API_BASE_URL?: string
  readonly VITE_SELLER_RPA_API_AUTH_HEADER?: string
  readonly VITE_SELLER_RPA_API_TOKEN?: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
