import axios, { AxiosHeaders, type AxiosError, type AxiosInstance, type AxiosRequestConfig, type AxiosResponse, type InternalAxiosRequestConfig } from 'axios'
import { emitNetworkLog } from '../debug/network-log'

const DEFAULT_TIMEOUT = 15000
const USE_DEV_PROXY = import.meta.env.VITE_USE_DEV_PROXY === 'true'
const OPENAPI_BASE_URL = USE_DEV_PROXY ? '' : import.meta.env.VITE_OPENAPI_BASE_URL || ''

export const httpClient: AxiosInstance = axios.create({
  baseURL: OPENAPI_BASE_URL,
  timeout: DEFAULT_TIMEOUT,
  headers: {
    'Content-Type': 'application/json'
  }
})

type IPCInvoke = (channel: string, ...args: any[]) => Promise<any>

interface RuntimeAuthState {
  token: string
  deviceId: string
  tokenName: string
  source: 'url' | 'runtime-auth' | 'global-state' | 'storage' | 'none'
}

const APP_GLOBAL_STATE_GET_ALL_CHANNEL = 'app-global-state-get-all'
const APP_GET_RUNTIME_AUTH_CHANNEL = 'app-get-runtime-auth'
const TOKEN_HEADER_KEY = 'xunda-token'
const DEVICE_ID_HEADER_KEY = 'xunda-device-id'
const TOKEN_NAME_STORAGE_KEY = 'xunda-token-name'
const URL_TOKEN_PARAM = 'xundaToken'
const URL_TOKEN_NAME_PARAM = 'xundaTokenName'
const URL_DEVICE_ID_PARAM = 'xundaDeviceId'

let requestSequence = 0
let pendingAuthState: Promise<RuntimeAuthState> | null = null
let warnedIpcUnavailable = false

interface RequestMeta {
  requestId: string
  startAt: number
}

interface RequestConfigWithMeta extends InternalAxiosRequestConfig {
  metadata?: RequestMeta
}

const normalizeString = (value: unknown): string => {
  return typeof value === 'string' ? value.trim() : ''
}

const toPlainHeaders = (headers: unknown): Record<string, any> => {
  if (!headers) return {}
  if (headers instanceof AxiosHeaders) return headers.toJSON()
  if (typeof (headers as any).toJSON === 'function') return (headers as any).toJSON()
  return headers as Record<string, any>
}

const resolveRequestUrl = (config: Pick<AxiosRequestConfig, 'baseURL' | 'url'>): string => {
  const rawUrl = normalizeString(config.url)
  if (!rawUrl) return ''
  if (/^https?:\/\//i.test(rawUrl)) return rawUrl

  const baseUrl = normalizeString(config.baseURL || httpClient.defaults.baseURL)
  if (!baseUrl) return rawUrl
  return `${baseUrl.replace(/\/+$/, '')}/${rawUrl.replace(/^\/+/, '')}`
}

const getWindowLogger = (): ((level: 'info' | 'error', message: string, payload: Record<string, any>) => void) => {
  const logger = (window as any).logger
  if (!logger) {
    return (level, message, payload) => {
      if (level === 'error') {
        console.error(message, payload)
      } else {
        console.info(message, payload)
      }
    }
  }

  return (level, message, payload) => {
    if (level === 'error') {
      console.error(message, payload)
      logger.error?.(message, payload)
      return
    }
    console.info(message, payload)
    logger.info?.(message, payload)
  }
}

const logWithDesktopStyle = getWindowLogger()

const logWithPanel = (level: 'info' | 'error', message: string, payload: Record<string, any>): void => {
  logWithDesktopStyle(level, message, payload)
  emitNetworkLog(level, message, payload)
}

const getGatewayByChannel = (channel: string): string => {
  if (channel.startsWith('app-')) return 'app'
  if (channel.startsWith('websocket-')) return 'ws'
  if (channel.startsWith('tk-')) return 'tk'
  if (channel.startsWith('tabs-')) return 'tab'
  if (channel.startsWith('rpa-')) return 'rpa'
  if (channel.startsWith('renderer-monitor-')) return 'monitor'
  return 'app'
}

const getFromStorage = (key: string): string => {
  try {
    const fromLocal = normalizeString(window.localStorage.getItem(key))
    if (fromLocal) return fromLocal
    return normalizeString(window.sessionStorage.getItem(key))
  } catch (_error) {
    return ''
  }
}

const saveToStorage = (key: string, value: string): void => {
  const normalizedValue = normalizeString(value)
  if (!normalizedValue) return
  try {
    window.localStorage.setItem(key, normalizedValue)
    window.sessionStorage.setItem(key, normalizedValue)
  } catch (_error) {
    // ignore storage errors in restricted contexts
  }
}

const persistAuthState = (state: RuntimeAuthState): RuntimeAuthState => {
  saveToStorage(TOKEN_HEADER_KEY, state.token)
  saveToStorage(DEVICE_ID_HEADER_KEY, state.deviceId)
  saveToStorage(TOKEN_NAME_STORAGE_KEY, state.tokenName)
  return state
}

const getAuthFromUrl = (): RuntimeAuthState | null => {
  try {
    const url = new URL(window.location.href)
    const token = normalizeString(url.searchParams.get(URL_TOKEN_PARAM))
    const tokenName = normalizeString(url.searchParams.get(URL_TOKEN_NAME_PARAM)) || TOKEN_HEADER_KEY
    const deviceId = normalizeString(url.searchParams.get(URL_DEVICE_ID_PARAM))
    if (!token && !deviceId) {
      return null
    }
    return {
      token,
      tokenName,
      deviceId,
      source: 'url'
    }
  } catch (_error) {
    return null
  }
}

const invokeDesktopChannel = async (channel: string, ...args: any[]): Promise<any> => {
  const typedInvoke = (window as any).ipc?.invoke as IPCInvoke | undefined
  if (typeof typedInvoke === 'function') {
    return await typedInvoke(channel, ...args)
  }

  const rawInvoke = (window as any).electron?.ipcRenderer?.invoke as ((channel: string, ...args: any[]) => Promise<any>) | undefined
  if (typeof rawInvoke === 'function') {
    const gateway = getGatewayByChannel(channel)
    return await rawInvoke(gateway, { channel, args })
  }

  if (!warnedIpcUnavailable) {
    warnedIpcUnavailable = true
    logWithPanel('error', '[AuthIPC] IPC bridge not available in current embed context', {
      hasWindowIpc: Boolean((window as any).ipc),
      hasElectronIpcRenderer: Boolean((window as any).electron?.ipcRenderer)
    })
  }
  throw new Error('IPC bridge not available in embed context')
}

const loadAuthState = async (): Promise<RuntimeAuthState> => {
  const urlAuth = getAuthFromUrl()
  if (urlAuth) {
    return persistAuthState(urlAuth)
  }

  try {
    const runtimeAuth = await invokeDesktopChannel(APP_GET_RUNTIME_AUTH_CHANNEL)
    const runtimeData = runtimeAuth?.data
    const runtimeToken = normalizeString(runtimeData?.token)
    const runtimeDeviceId = normalizeString(runtimeData?.deviceId)
    const runtimeTokenName = normalizeString(runtimeData?.tokenName) || TOKEN_HEADER_KEY

    if (runtimeAuth?.success && (runtimeToken || runtimeDeviceId)) {
      return persistAuthState({
        token: runtimeToken,
        deviceId: runtimeDeviceId,
        tokenName: runtimeTokenName,
        source: 'runtime-auth'
      })
    }
  } catch (_error) {
    // ignore and continue fallbacks
  }

  try {
    const result = await invokeDesktopChannel(APP_GLOBAL_STATE_GET_ALL_CHANNEL)
    const state = result?.data
    const token = normalizeString(state?.currentUser?.tokenValue)
    const deviceId = normalizeString(state?.appInfo?.deviceId)
    const tokenName = normalizeString(state?.currentUser?.tokenName) || TOKEN_HEADER_KEY
    if (token || deviceId) {
      return persistAuthState({ token, deviceId, tokenName, source: 'global-state' })
    }
  } catch (_error) {
    // ignore and continue fallbacks
  }

  const storageToken = getFromStorage(TOKEN_HEADER_KEY)
  const storageDeviceId = getFromStorage(DEVICE_ID_HEADER_KEY)
  const storageTokenName = getFromStorage(TOKEN_NAME_STORAGE_KEY) || TOKEN_HEADER_KEY
  if (storageToken || storageDeviceId) {
    return {
      token: storageToken,
      deviceId: storageDeviceId,
      tokenName: storageTokenName,
      source: 'storage'
    }
  }

  return {
    token: '',
    deviceId: '',
    tokenName: TOKEN_HEADER_KEY,
    source: 'none'
  }
}

const getAuthState = async (): Promise<RuntimeAuthState> => {
  if (!pendingAuthState) {
    pendingAuthState = loadAuthState().finally(() => {
      pendingAuthState = null
    })
  }
  return await pendingAuthState
}

httpClient.interceptors.request.use(async (config: InternalAxiosRequestConfig) => {
  const requestId = `embed-${Date.now()}-${++requestSequence}`
  ;(config as RequestConfigWithMeta).metadata = {
    requestId,
    startAt: Date.now()
  }

  const auth = await getAuthState()
  const headers = AxiosHeaders.from(config.headers || {})
  if (auth.token) {
    headers.set(TOKEN_HEADER_KEY, auth.token)
    if (auth.tokenName && auth.tokenName !== TOKEN_HEADER_KEY) {
      headers.set(auth.tokenName, auth.token)
    }
  }
  if (auth.deviceId) {
    headers.set(DEVICE_ID_HEADER_KEY, auth.deviceId)
  }
  config.headers = headers

  logWithPanel('info', '[Request]', {
    requestId,
    method: normalizeString(config.method).toUpperCase() || 'GET',
    url: resolveRequestUrl(config),
    auth: {
      source: auth.source,
      hasToken: Boolean(auth.token),
      tokenName: auth.tokenName || TOKEN_HEADER_KEY,
      hasDeviceId: Boolean(auth.deviceId)
    },
    params: config.params,
    headers: toPlainHeaders(config.headers),
    data: config.data
  })

  return config
})

httpClient.interceptors.response.use(
  (response: AxiosResponse) => {
    const config = response.config as RequestConfigWithMeta
    const requestId = config.metadata?.requestId || ''
    const durationMs = config.metadata?.startAt ? Date.now() - config.metadata.startAt : undefined

    logWithPanel('info', '[Response]', {
      requestId,
      method: normalizeString(config.method).toUpperCase() || 'GET',
      url: resolveRequestUrl(config),
      status: response.status,
      durationMs,
      headers: toPlainHeaders(response.headers),
      data: response.data
    })

    return response
  },
  (error: AxiosError) => {
    const config = (error.config || {}) as RequestConfigWithMeta
    const requestId = config.metadata?.requestId || ''
    const durationMs = config.metadata?.startAt ? Date.now() - config.metadata.startAt : undefined
    const requestUrl = resolveRequestUrl(config)

    if (error.response) {
      logWithPanel('error', '❌ 响应错误:', {
        requestId,
        method: normalizeString(config.method).toUpperCase() || 'GET',
        url: requestUrl,
        status: error.response.status,
        durationMs,
        requestHeaders: toPlainHeaders(config.headers),
        data: error.response.data,
        headers: toPlainHeaders(error.response.headers)
      })
    } else {
      logWithPanel('error', `Embed 网络错误或请求超时 [${requestUrl}]: ${error.message}`, {
        requestId,
        method: normalizeString(config.method).toUpperCase() || 'GET',
        url: requestUrl,
        durationMs,
        requestHeaders: toPlainHeaders(config.headers)
      })
    }

    return Promise.reject(error)
  }
)

export const request = async <T = unknown>(config: AxiosRequestConfig): Promise<T> => {
  const response = await httpClient.request<T>(config)
  return response.data
}
