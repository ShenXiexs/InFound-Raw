import { IncomingMessage, net } from 'electron'
import { logger } from './logger'
import { AppConfig } from '@common/app-config'
import { CookieMap, parseSetCookie } from './set-cookie-parser'
import { appStore } from '../modules/store/app-store'

export type BaseApiResponse<T = any> = {
  code: number
  msg: string
  data?: T
}

export interface RequestOptions {
  globalErrorMessage?: boolean
  globalSuccessMessage?: boolean
}

export interface InterceptorHooks {
  requestInterceptor?: (config: NetRequestConfig) => NetRequestConfig
  requestInterceptorErrorCatch?: (error: any) => any
  responseInterceptor?: (response: NetResponse) => NetResponse | Promise<NetResponse>
  responseInterceptorErrorCatch?: (error: any) => any
}

// Electron net 封装的请求配置
export interface NetRequestConfig {
  method?: 'GET' | 'POST' | 'PUT' | 'DELETE'
  url: string
  headers?: Record<string, string>
  body?: any
  timeout?: number
  requestOptions?: RequestOptions
}

export interface NetResponse<T = any> {
  status: number
  headers: Record<string, string | string[]>
  data: T
  config: NetRequestConfig
}

export default class NetRequest {
  private _axiosApiCookie: string | undefined
  private _interceptorHooks?: InterceptorHooks

  constructor(interceptorHooks?: InterceptorHooks) {
    this._interceptorHooks = interceptorHooks
  }

  // 核心 request 方法
  public request<T = any>(config: NetRequestConfig): Promise<NetResponse<T>> {
    return new Promise<NetResponse<T>>((resolve, reject) => {
      try {
        // 处理拦截器：request
        if (!this._axiosApiCookie) {
          this._axiosApiCookie = appStore.get('apiCookie')
        }

        const headersWithCookie = {
          ...config.headers
        }
        if (this._axiosApiCookie) {
          headersWithCookie['Cookie'] = this._axiosApiCookie
        }

        const finalConfig = this._interceptorHooks?.requestInterceptor?.({
          ...config,
          headers: headersWithCookie
        }) || {
          ...config,
          headers: headersWithCookie
        }

        // 自动解析 xunda_token
        if (this._axiosApiCookie) {
          const cookieMap: CookieMap = parseSetCookie(this._axiosApiCookie, { map: true })
          const tokenName = cookieMap['xunda_token_name']
          const tokenValue = cookieMap['xunda_token_value']
          if (tokenName && tokenValue) {
            finalConfig.headers![tokenName.value] = tokenValue.value
          }
        }

        const request = net.request({
          method: finalConfig.method || 'GET',
          url: AppConfig.OPENAPI_BASE_URL + finalConfig.url
        })

        // 设置 headers
        if (finalConfig.headers) {
          for (const key in finalConfig.headers) {
            if (finalConfig.headers[key] !== undefined) {
              request.setHeader(key, finalConfig.headers[key])
            }
          }
        }

        // timeout
        let timeoutId: NodeJS.Timeout | null = null
        if (finalConfig.timeout) {
          timeoutId = setTimeout(() => {
            request.abort()
            reject(new Error(`Request timeout after ${finalConfig.timeout}ms`))
          }, finalConfig.timeout)
        }

        // 监听响应
        request.on('response', (response: IncomingMessage) => {
          const chunks: Buffer[] = []
          response.on('data', (chunk: Buffer) => chunks.push(chunk))
          response.on('end', async () => {
            if (timeoutId) clearTimeout(timeoutId)
            const rawData = Buffer.concat(chunks).toString()

            let parsedData: any = rawData
            const contentType = response.headers['content-type']
            if (contentType && contentType.toString().includes('application/json')) {
              try {
                parsedData = JSON.parse(rawData)
              } catch (err) {
                // 解析失败保持原始字符串
              }
            }

            // 保存 set-cookie
            const setCookie = response.headers['set-cookie']
            if (setCookie) {
              this._axiosApiCookie = setCookie as string
              appStore.set('apiCookie', this._axiosApiCookie)
            }

            const netResponse: NetResponse<T> = {
              status: response.statusCode,
              headers: response.headers,
              data: parsedData,
              config: finalConfig
            }

            try {
              const finalResponse = await (this._interceptorHooks?.responseInterceptor?.(netResponse) || netResponse)
              resolve(finalResponse)
            } catch (hookErr) {
              reject(hookErr)
            }
          })
        })

        request.on('error', (err) => {
          if (timeoutId) clearTimeout(timeoutId)
          const error = this._interceptorHooks?.responseInterceptorErrorCatch?.(err) || err
          reject(error)
        })

        // 写入 body
        if (finalConfig.body) {
          if (typeof finalConfig.body === 'object' && !Buffer.isBuffer(finalConfig.body)) {
            request.setHeader('Content-Type', 'application/json')
            request.write(JSON.stringify(finalConfig.body))
          } else {
            request.write(finalConfig.body)
          }
        }

        request.end()
      } catch (err) {
        reject(err)
      }
    })
  }

  // get/post/put/delete 方法封装
  public async get<T = any>(url: string, config?: NetRequestConfig): Promise<T> {
    const response = await this.request<T>({ ...config, method: 'GET', url })
    return response.data
  }

  public async post<T = any>(url: string, data?: any, config?: NetRequestConfig): Promise<T> {
    const response = await this.request<T>({ ...config, method: 'POST', url, body: data })
    logger.info('Post Response: ' + JSON.stringify(response.data))
    return response.data
  }

  public async put<T = any>(url: string, data?: any, config?: NetRequestConfig): Promise<T> {
    const response = await this.request<T>({ ...config, method: 'PUT', url, body: data })
    return response.data
  }

  public async delete<T = any>(url: string, config?: NetRequestConfig): Promise<T> {
    const response = await this.request<T>({ ...config, method: 'DELETE', url })
    return response.data
  }
}
