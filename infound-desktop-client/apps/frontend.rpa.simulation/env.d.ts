interface ImportMetaEnv {
  readonly VITE_LOG_LEVEL: string
  readonly VITE_LOG_ENABLE: string
  readonly VITE_APP_NAME: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
