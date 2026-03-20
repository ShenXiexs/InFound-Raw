import type { CDPSession, Page } from 'playwright'
import type { TaskLoggerLike } from '../task-dsl/types'

export interface CapturedJsonResponse {
  url: string
  body: unknown
  captured_at: string
}

interface JsonResponseCaptureSession {
  captureKey: string
  urlIncludes: string
  requestMethod?: string
  responses: CapturedJsonResponse[]
  matchedRequestIds: Set<string>
  processedRequestIds: Set<string>
  requestUrlById: Map<string, string>
  pendingTasks: Set<Promise<void>>
  reachedEndByApi: boolean
  cdpSession: CDPSession
  listener: (method: string, params: Record<string, unknown>) => void
}

const sleep = async (ms: number): Promise<void> => {
  await new Promise((resolve) => setTimeout(resolve, ms))
}

export class PlaywrightJsonResponseCaptureManager {
  private readonly captureSessions = new Map<string, JsonResponseCaptureSession>()

  constructor(private readonly logger: TaskLoggerLike) {}

  public async startJsonResponseCapture(
    page: Page,
    options: { captureKey: string; urlIncludes: string; method?: string; reset?: boolean }
  ): Promise<void> {
    const captureKey = String(options.captureKey || '').trim()
    const urlIncludes = String(options.urlIncludes || '').trim()
    const requestMethod = String(options.method || '')
      .trim()
      .toUpperCase()

    if (!captureKey) {
      throw new Error('captureKey 不能为空')
    }
    if (!urlIncludes) {
      throw new Error('urlIncludes 不能为空')
    }

    if (options.reset !== false) {
      await this.disposeJsonResponseCaptureSession(page, captureKey)
    }

    const cdpSession = await page.context().newCDPSession(page)
    await cdpSession.send('Network.enable')

    const session: JsonResponseCaptureSession = {
      captureKey,
      urlIncludes,
      requestMethod: requestMethod || undefined,
      responses: [],
      matchedRequestIds: new Set<string>(),
      processedRequestIds: new Set<string>(),
      requestUrlById: new Map<string, string>(),
      pendingTasks: new Set<Promise<void>>(),
      reachedEndByApi: false,
      cdpSession,
      listener: (method, params) => {
        if (method === 'Network.requestWillBeSent') {
          const requestId = String(params?.requestId || '')
          const request = (params?.request || {}) as Record<string, unknown>
          const url = String(request.url || '')
          const currentMethod = String(request.method || '')
            .trim()
            .toUpperCase()
          const matchedMethod = !session.requestMethod || currentMethod === session.requestMethod
          if (requestId && url.includes(urlIncludes) && matchedMethod) {
            session.matchedRequestIds.add(requestId)
            session.requestUrlById.set(requestId, url)
            this.logger.info(`Playwright CDP 已匹配请求: key=${captureKey} method=${currentMethod} url=${url}`)
          }
          return
        }

        if (method === 'Network.responseReceived') {
          const requestId = String(params?.requestId || '')
          if (!requestId || !session.matchedRequestIds.has(requestId)) {
            return
          }

          const response = (params?.response || {}) as Record<string, unknown>
          const mimeType = String(response.mimeType || '')
          const resourceType = String(params?.type || '')
          const matchedJsonLike = resourceType === 'XHR' || resourceType === 'Fetch' || mimeType.includes('json')
          if (!matchedJsonLike) {
            session.matchedRequestIds.delete(requestId)
            session.requestUrlById.delete(requestId)
            this.logger.warn(
              `Playwright CDP 请求已命中但响应类型非 JSON: key=${captureKey} type=${resourceType || '(empty)'} mime=${mimeType || '(empty)'} url=${session.requestUrlById.get(requestId) || ''}`
            )
          }
          return
        }

        if (method !== 'Network.loadingFinished') {
          return
        }

        const requestId = String(params?.requestId || '')
        if (!requestId || !session.matchedRequestIds.has(requestId) || session.processedRequestIds.has(requestId)) {
          return
        }

        session.processedRequestIds.add(requestId)
        const task = (async () => {
          try {
            const responseBody = (await session.cdpSession.send('Network.getResponseBody', {
              requestId
            })) as { body?: string; base64Encoded?: boolean }

            const rawBody = responseBody.base64Encoded
              ? Buffer.from(String(responseBody.body || ''), 'base64').toString('utf8')
              : String(responseBody.body || '')
            if (!rawBody) return

            const parsedBody = JSON.parse(rawBody)
            session.responses.push({
              url: session.requestUrlById.get(requestId) || '',
              body: parsedBody,
              captured_at: new Date().toISOString()
            })

            const hasMore = this.readHasMoreFlag(parsedBody)
            if (hasMore === false) {
              session.reachedEndByApi = true
            }

            this.logger.info(
              `Playwright CDP 已捕获响应: key=${captureKey} url=${session.requestUrlById.get(requestId) || ''}`
            )
          } catch (error) {
            this.logger.warn(
              `Playwright CDP 响应捕获失败: url=${session.requestUrlById.get(requestId) || ''} message=${(error as Error)?.message || error}`
            )
          }
        })()

        session.pendingTasks.add(task)
        void task.finally(() => {
          session.pendingTasks.delete(task)
          session.matchedRequestIds.delete(requestId)
          session.requestUrlById.delete(requestId)
        })
      }
    }

    cdpSession.on('Network.requestWillBeSent', (params) => {
      session.listener('Network.requestWillBeSent', params as Record<string, unknown>)
    })
    cdpSession.on('Network.responseReceived', (params) => {
      session.listener('Network.responseReceived', params as Record<string, unknown>)
    })
    cdpSession.on('Network.loadingFinished', (params) => {
      session.listener('Network.loadingFinished', params as Record<string, unknown>)
    })

    this.captureSessions.set(captureKey, session)
    this.logger.info(
      `启动 Playwright JSON 响应捕获: key=${captureKey} urlIncludes=${urlIncludes}${session.requestMethod ? ` method=${session.requestMethod}` : ''}`
    )
  }

  public async disposeJsonResponseCaptureSession(_page: Page, captureKey: string): Promise<CapturedJsonResponse[]> {
    const session = this.captureSessions.get(captureKey)
    if (!session) return []

    await Promise.allSettled(Array.from(session.pendingTasks))
    await session.cdpSession.detach().catch(() => undefined)
    this.captureSessions.delete(captureKey)
    return session.responses
  }

  public getResponses(captureKey: string): CapturedJsonResponse[] {
    return this.captureSessions.get(captureKey)?.responses ?? []
  }

  public hasReachedEndByApi(captureKey: string): boolean {
    return Boolean(this.captureSessions.get(captureKey)?.reachedEndByApi)
  }

  public async waitForNextParsedResponse<T>(options: {
    captureKey: string
    responseCursor: number
    timeoutMs: number
    parse: (captured: CapturedJsonResponse, responseIndex: number) => { key: string; value: T } | null
    knownKeys?: Set<string>
  }): Promise<{ key: string; value: T; nextCursor: number } | null> {
    const deadline = Date.now() + options.timeoutMs
    let cursor = options.responseCursor

    while (Date.now() < deadline) {
      const responses = this.getResponses(options.captureKey)

      while (cursor < responses.length) {
        const currentIndex = cursor
        const captured = responses[cursor]
        cursor += 1
        const parsed = options.parse(captured, currentIndex)
        if (!parsed) {
          continue
        }
        if (options.knownKeys?.has(parsed.key)) {
          continue
        }
        return {
          ...parsed,
          nextCursor: cursor
        }
      }

      await sleep(250)
    }

    return null
  }

  private readHasMoreFlag(payload: unknown): boolean | undefined {
    const candidatePaths = ['data.has_more', 'pagination.has_more', 'next_pagination.has_more', 'has_more']
    for (const path of candidatePaths) {
      const value = path.split('.').reduce<unknown>((current, segment) => {
        if (current === null || current === undefined) return undefined
        if (typeof current !== 'object') return undefined
        return (current as Record<string, unknown>)[segment]
      }, payload)
      if (typeof value === 'boolean') {
        return value
      }
    }
    return undefined
  }
}
