interface ImportMetaEnv {
  readonly VITE_LOG_LEVEL: string
  readonly VITE_LOG_ENABLE: string
  readonly VITE_APP_PROTOCOL: string
  readonly VITE_APP_HARDCODED_SALT: string
  readonly VITE_OPENAPI_BASE_URL: string
  readonly VITE_WS_BASE_URL: string
  readonly VITE_DOWNLOAD_BASE_URL: string
  readonly VITE_OFFICIAL_WEBSITE_BASE_URL: string
  readonly VITE_EMBED_BASE_URL: string
}

interface ImportMeta {
  readonly env: ImportMetaEnv
}
