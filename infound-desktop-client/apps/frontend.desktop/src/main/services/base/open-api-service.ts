import { logger } from '../../utils/logger'
import NetRequest, { InterceptorHooks } from '../../utils/net-request'
import { globalState } from '../../modules/state/global-state'
import { HTTP_HEADERS } from '@common/app-constants'
import { AppConfig } from '@common/app-config'

const transform: InterceptorHooks = {
  requestInterceptor(config) {
    const appInfo = globalState.currentState.appInfo

    config.headers = config.headers || {}

    if (appInfo.deviceId) {
      config.headers[HTTP_HEADERS.DEVICE_ID] = appInfo.deviceId
    }
    if (appInfo.name) {
      config.headers[HTTP_HEADERS.APP_KEY] = appInfo.name
    }
    if (appInfo.version) {
      config.headers[HTTP_HEADERS.APP_VERSION] = appInfo.version
    }

    config.headers[HTTP_HEADERS.APP_TYPE] = 'desktop'

    const currentUser = globalState.currentState.currentUser
    if (currentUser?.tokenName && currentUser?.tokenValue) {
      config.headers[currentUser.tokenName] = currentUser.tokenValue
    }

    if (!AppConfig.IS_PRO) {
      logger.info('[Request]', {
        method: config.method,
        url: config.url,
        headers: config.headers,
        data: config.body
      })
    }

    return config
  },
  requestInterceptorErrorCatch(error) {
    return Promise.reject(error)
  },
  responseInterceptor(response) {
    try {
      if (!AppConfig.IS_PRO) {
        logger.info('[Response]', {
          status: response.status,
          headers: response.headers,
          data: response.data,
          dataStr: JSON.stringify(response.data)
        })
      }

      if (response.status !== 200) {
        logger.error(`Request failed, the status code is ${response.status}`)
      }

      if (response?.data?.code === 3001) {
        logger.error('Login failed: ' + response.data.msg)
        throw new Error(response.data.msg)
      }

      return response
    } finally {
      // noop
    }
  },
  responseInterceptorErrorCatch(error) {
    if ((error as any)?.status) {
      logger.error('❌ 响应错误:', {
        status: (error as any).status,
        data: (error as any).data,
        headers: (error as any).headers
      })
    } else {
      const requestUrl = (error as any)?.config?.url
      logger.error('Main 网络错误或请求超时 [' + requestUrl + ']: ' + error.message)
    }
    return Promise.reject(error)
  }
}

const openapiRequest = new NetRequest(transform)

export default openapiRequest
