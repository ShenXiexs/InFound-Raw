import { BaseWindow, session, WebContentsView } from 'electron'
import { join } from 'path'
import { logger } from '../utils/logger'
import { AppConfig } from '@common/app-config'
import type { BrowserPaginationResult, BrowserSelectorState } from '../modules/rpa/task-dsl/browser-actions'

interface JsonResponseCaptureSession {
  captureKey: string
  urlIncludes: string
  requestMethod?: string
  responses: unknown[]
  matchedRequestIds: Set<string>
  processedRequestIds: Set<string>
  pendingTasks: Set<Promise<void>>
  reachedEndByApi: boolean
  listener: (_event: Electron.Event, method: string, params: Record<string, unknown>) => void
}

interface ScrollProgressResult {
  moved: boolean
  reachedEnd: boolean
  scrollTop: number
  maxScrollTop: number
}

export class TkWcv {
  private baseWindow: BaseWindow | null = null
  private tkWCV: WebContentsView | null = null
  private loginMonitorTimer: ReturnType<typeof setInterval> | null = null
  private loginMonitorInProgress = false
  private loginMonitorStartedAt = 0
  private readonly loginSuccessText = 'Proven strategies to grow your business'
  private readonly loginDetectIntervalMs = 2000
  private readonly loginDetectTimeoutMs = 30 * 60 * 1000
  private readonly jsonResponseCaptures = new Map<string, JsonResponseCaptureSession>()

  constructor() {
    this.baseWindow = null
    this.tkWCV = null
  }

  public async initView(mainWindow: BaseWindow): Promise<void> {
    this.baseWindow = mainWindow

    const persistKey = 'persist:TKWindow'
    const sess = session.fromPartition(persistKey)

    sess.webRequest.onBeforeRequest((details, callback) => {
      if (details.url.startsWith('bytedance://')) {
        logger.info('拦截 bytedance 协议')
        return callback({ cancel: true })
      }
      callback({ cancel: false })
    })

    this.tkWCV = new WebContentsView({
      webPreferences: {
        partition: persistKey,
        preload: join(__dirname, '../preload/index.js'),
        session: sess,
        devTools: !AppConfig.IS_PRO,
        contextIsolation: true, // 强制开启，防止网页 JS 访问主进程模块
        nodeIntegration: false, // 严禁 Node.js 环境
        sandbox: false, // 开启沙盒，这是防止调用系统底层 Shell 的最强防线
        safeDialogs: true,
        webSecurity: true,
        allowRunningInsecureContent: false,
        plugins: false, // 严禁插件，防止插件触发系统调用
        webviewTag: false // 禁用 webview 标签
      }
    })

    this.tkWCV.webContents.setUserAgent(AppConfig.USER_AGENT)

    //monitorNavigation(logger, this.tkWCV.webContents)
    ;(this.tkWCV.webContents as any).on('will-frame-navigate', (event, url) => {
      if (!url.startsWith('http') && !url.startsWith('https')) {
        logger.warn(`拦截到子框架的协议跳转: ${url}`)
        event.preventDefault() // 这一步在子框架中同样有效
      }
    })

    // 监听渲染进程崩溃
    this.tkWCV.webContents.on('render-process-gone', (_event: Electron.Event, details: Electron.RenderProcessGoneDetails) => {
      const { reason } = details
      logger.error(`渲染进程崩溃: ${reason === 'killed' ? '被杀死' : '意外崩溃'}`)
      logger.error(`崩溃页面: ${this.tkWCV?.webContents.getURL()}`)
      this.stopSellerLoginSuccessMonitor()
    })

    // 监听渲染进程无响应
    this.tkWCV.webContents.on('unresponsive', () => {
      logger.error('渲染进程无响应')
      this.stopSellerLoginSuccessMonitor()
    })

    this.tkWCV.setVisible(false)

    //await this.tkWCV.webContents.loadURL('https://seller-mx.tiktok.com/')

    this.baseWindow.contentView.addChildView(this.tkWCV)

    logger.info('TKWindow 初始化成功')
  }

  public async openView(url: string | null): Promise<void> {
    this.baseWindow!.contentView.addChildView(this.tkWCV!)

    try {
      if (url) await this.tkWCV!.webContents.loadURL(url)
    } catch (err) {
      logger.error('加载失败，尝试重新初始化 session 或清理缓存...')
      // 如果失败，考虑清除缓存或 partition
      await this.tkWCV!.webContents.session.clearCache()
    }

    this.resize()
  }

  public startSellerLoginSuccessMonitor(): void {
    if (this.loginMonitorTimer) {
      logger.info('登录成功检测已在运行，跳过重复启动')
      return
    }

    this.loginMonitorStartedAt = Date.now()
    logger.info(`启动登录成功检测，轮询间隔 ${this.loginDetectIntervalMs}ms`)

    this.loginMonitorTimer = setInterval(() => {
      void this.checkSellerLoginSuccess()
    }, this.loginDetectIntervalMs)
  }

  public stopSellerLoginSuccessMonitor(): void {
    if (this.loginMonitorTimer) {
      clearInterval(this.loginMonitorTimer)
      this.loginMonitorTimer = null
    }
    this.loginMonitorInProgress = false
    this.loginMonitorStartedAt = 0
  }

  private async checkSellerLoginSuccess(): Promise<void> {
    if (this.loginMonitorInProgress) return

    if (this.loginMonitorStartedAt && Date.now() - this.loginMonitorStartedAt > this.loginDetectTimeoutMs) {
      logger.warn('登录成功检测超时，停止轮询')
      this.stopSellerLoginSuccessMonitor()
      return
    }

    const wc = this.tkWCV?.webContents
    if (!wc || wc.isDestroyed()) {
      this.stopSellerLoginSuccessMonitor()
      return
    }

    this.loginMonitorInProgress = true
    try {
      const result = await wc.executeJavaScript(
        `(() => {
          const bodyText = document?.body?.innerText || ''
          const hasSuccessText = bodyText.includes(${JSON.stringify(this.loginSuccessText)})
          return { hasSuccessText, href: location.href }
        })()`
      )

      if (!result?.hasSuccessText) return

      const href = String(result?.href || '')
      const region = this.extractShopRegion(href)
      if (!region) {
        logger.warn(`检测到登录成功文案，但无法从 URL 提取 shop_region: ${href}`)
        return
      }
      logger.info(`检测到登录成功，保持当前页面不跳转: ${href}`)
      logger.info(`已记录登录态与店铺区域: shop_region=${region}，等待后续任务指令`)
      this.stopSellerLoginSuccessMonitor()
    } catch (err) {
      logger.warn(`登录检测执行失败: ${(err as Error)?.message || err}`)
    } finally {
      this.loginMonitorInProgress = false
    }
  }

  public async waitForBodyText(text: string, timeoutMs = 30000, intervalMs = 500): Promise<boolean> {
    return this.waitUntilBodyContainsText(text, timeoutMs, intervalMs)
  }

  public async waitForSelector(
    selector: string,
    options?: { state?: BrowserSelectorState; timeoutMs?: number; intervalMs?: number }
  ): Promise<boolean> {
    const wc = this.tkWCV?.webContents
    if (!wc || wc.isDestroyed()) {
      return false
    }

    const state = options?.state ?? 'present'
    const timeoutMs = Math.max(1000, Number(options?.timeoutMs ?? 10000))
    const intervalMs = Math.max(50, Number(options?.intervalMs ?? 250))

    const result = await wc.executeJavaScript(
      `(() => {
        const selector = ${JSON.stringify(selector)}
        const state = ${JSON.stringify(state)}
        const timeoutMs = ${JSON.stringify(timeoutMs)}
        const intervalMs = ${JSON.stringify(intervalMs)}

        const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
        const isVisible = (element) => {
          if (!(element instanceof HTMLElement)) return false
          const style = window.getComputedStyle(element)
          if (style.display === 'none' || style.visibility === 'hidden') return false
          return element.offsetParent !== null || style.position === 'fixed'
        }
        const match = () => {
          const nodes = Array.from(document.querySelectorAll(selector))
          if (state === 'present') return nodes.length > 0
          if (state === 'visible') return nodes.some((node) => isVisible(node))
          if (state === 'absent') return nodes.length === 0
          if (state === 'hidden') return nodes.length > 0 && nodes.every((node) => !isVisible(node))
          return false
        }

        return (async () => {
          const startedAt = Date.now()
          while (Date.now() - startedAt < timeoutMs) {
            if (match()) return true
            await sleep(intervalMs)
          }
          return false
        })()
      })()`,
      true
    )

    return Boolean(result)
  }

  private async resolveClickablePoint(selector: string): Promise<{ x: number; y: number } | null> {
    const wc = this.tkWCV?.webContents
    if (!wc || wc.isDestroyed()) {
      return null
    }

    const point = await wc.executeJavaScript(
      `(() => {
        const selector = ${JSON.stringify(selector)}
        const isVisible = (element) => {
          if (!(element instanceof HTMLElement)) return false
          const style = window.getComputedStyle(element)
          if (style.display === 'none' || style.visibility === 'hidden') return false
          const rect = element.getBoundingClientRect()
          return rect.width > 0 && rect.height > 0 && (element.offsetParent !== null || style.position === 'fixed')
        }

        return (async () => {
          const candidates = Array.from(document.querySelectorAll(selector))
          const node = candidates.find((candidate) => isVisible(candidate)) || candidates[0] || null
          if (!(node instanceof HTMLElement)) return null

          node.scrollIntoView({ block: 'center', inline: 'center' })
          if (typeof node.focus === 'function') {
            node.focus({ preventScroll: true })
          }

          await new Promise((resolve) => requestAnimationFrame(() => requestAnimationFrame(resolve)))

          const rect = node.getBoundingClientRect()
          if (!rect.width || !rect.height) return null

          const x = Math.round(rect.left + rect.width / 2)
          const y = Math.round(rect.top + rect.height / 2)
          const topNode = document.elementFromPoint(x, y)
          if (!topNode) return { x, y }

          if (topNode === node || node.contains(topNode) || topNode.contains(node)) {
            return { x, y }
          }

          return { x, y }
        })()
      })()`,
      true
    )

    if (!point || typeof point.x !== 'number' || typeof point.y !== 'number') {
      return null
    }

    return {
      x: Math.max(1, Math.round(point.x)),
      y: Math.max(1, Math.round(point.y))
    }
  }

  public async clickSelector(selector: string, options?: { native?: boolean }): Promise<void> {
    const wc = this.tkWCV?.webContents
    if (!wc || wc.isDestroyed()) {
      throw new Error('WebContents 不可用，无法执行 clickSelector')
    }

    if (options?.native) {
      const point = await this.resolveClickablePoint(selector)
      if (!point) {
        throw new Error(`clickSelector 失败：未找到元素 ${selector}`)
      }

      wc.focus()
      wc.sendInputEvent({ type: 'mouseMove', x: point.x, y: point.y })
      await new Promise((resolve) => setTimeout(resolve, 16))
      wc.sendInputEvent({ type: 'mouseDown', x: point.x, y: point.y, button: 'left', clickCount: 1 })
      await new Promise((resolve) => setTimeout(resolve, 16))
      wc.sendInputEvent({ type: 'mouseUp', x: point.x, y: point.y, button: 'left', clickCount: 1 })
      return
    }

    const clicked = await wc.executeJavaScript(
      `(() => {
        const selector = ${JSON.stringify(selector)}
        const isVisible = (element) => {
          if (!(element instanceof HTMLElement)) return false
          const style = window.getComputedStyle(element)
          if (style.display === 'none' || style.visibility === 'hidden') return false
          return element.offsetParent !== null || style.position === 'fixed'
        }
        const candidates = Array.from(document.querySelectorAll(selector))
        const node = candidates.find((candidate) => isVisible(candidate)) || candidates[0] || null
        if (!node) return false
        if (node instanceof HTMLElement && typeof node.scrollIntoView === 'function') {
          node.scrollIntoView({ block: 'center', inline: 'nearest' })
        }
        if (typeof node.click === 'function') {
          node.click()
          return true
        }
        node.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
        return true
      })()`,
      true
    )

    if (!clicked) {
      throw new Error(`clickSelector 失败：未找到元素 ${selector}`)
    }
  }

  public async clickByText(
    text: string,
    options: {
      selector: string
      exact?: boolean
      caseSensitive?: boolean
      timeoutMs?: number
      intervalMs?: number
      scrollContainerSelector?: string
      scrollStepPx?: number
      maxScrollAttempts?: number
    }
  ): Promise<void> {
    const wc = this.tkWCV?.webContents
    if (!wc || wc.isDestroyed()) {
      throw new Error('WebContents 不可用，无法执行 clickByText')
    }

    const selector = options.selector
    const exact = Boolean(options.exact ?? true)
    const caseSensitive = Boolean(options.caseSensitive ?? false)
    const timeoutMs = Math.max(1000, Number(options.timeoutMs ?? 10000))
    const intervalMs = Math.max(50, Number(options.intervalMs ?? 250))
    const scrollContainerSelector = String(options.scrollContainerSelector || '')
    const scrollStepPx = Math.max(40, Number(options.scrollStepPx ?? 320))
    const maxScrollAttempts = Math.max(0, Number(options.maxScrollAttempts ?? 0))

    const clicked = await wc.executeJavaScript(
      `(() => {
        const targetText = ${JSON.stringify(text)}
        const selector = ${JSON.stringify(selector)}
        const exact = ${JSON.stringify(exact)}
        const caseSensitive = ${JSON.stringify(caseSensitive)}
        const timeoutMs = ${JSON.stringify(timeoutMs)}
        const intervalMs = ${JSON.stringify(intervalMs)}
        const scrollContainerSelector = ${JSON.stringify(scrollContainerSelector)}
        const scrollStepPx = ${JSON.stringify(scrollStepPx)}
        const maxScrollAttempts = ${JSON.stringify(maxScrollAttempts)}

        const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
        const normalize = (value) => String(value ?? '').replace(/\\s+/g, ' ').trim()
        const normalizeCase = (value) => (caseSensitive ? value : value.toLowerCase())
        const expected = normalizeCase(normalize(targetText))
        const isVisible = (element) => {
          if (!(element instanceof HTMLElement)) return false
          const style = window.getComputedStyle(element)
          if (style.display === 'none' || style.visibility === 'hidden') return false
          return element.offsetParent !== null || style.position === 'fixed'
        }

        const findMatch = () => {
          const candidates = Array.from(document.querySelectorAll(selector))
          return candidates.find((node) => {
            if (!isVisible(node)) return false
            const textValue = normalizeCase(normalize(node.textContent))
            if (!textValue) return false
            return exact ? textValue === expected : textValue.includes(expected)
          })
        }

        const scrollVisibleContainers = () => {
          if (!scrollContainerSelector) return false
          const containers = Array.from(document.querySelectorAll(scrollContainerSelector)).filter((node) => isVisible(node))
          let moved = false
          for (const container of containers) {
            if (!(container instanceof HTMLElement)) continue
            const previousTop = container.scrollTop
            const nextTop = Math.min(previousTop + scrollStepPx, Math.max(0, container.scrollHeight - container.clientHeight))
            if (nextTop !== previousTop) {
              container.scrollTop = nextTop
              container.dispatchEvent(new Event('scroll', { bubbles: true }))
              moved = true
            }
          }
          return moved
        }

        return (async () => {
          const startedAt = Date.now()
          let scrollAttempts = 0
          while (Date.now() - startedAt < timeoutMs) {
            const target = findMatch()
            if (target) {
              const wrapper =
                target instanceof Element
                  ? target.closest('li[role="option"], .arco-select-option-wrapper')
                  : null
              const checkbox =
                wrapper instanceof Element ? wrapper.querySelector('input[type="checkbox"]') : null
              const checkboxLabel =
                wrapper instanceof Element ? wrapper.querySelector('label.arco-checkbox, label') : null

              if (checkbox instanceof HTMLInputElement) {
                if (checkbox.checked) {
                  return true
                }
                const checkboxClickTarget = checkboxLabel instanceof HTMLElement ? checkboxLabel : checkbox
                if (typeof checkboxClickTarget.scrollIntoView === 'function') {
                  checkboxClickTarget.scrollIntoView({ block: 'nearest', inline: 'nearest' })
                }
                if (typeof checkboxClickTarget.click === 'function') {
                  checkboxClickTarget.click()
                } else {
                  checkboxClickTarget.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
                }
                await sleep(60)
                if (!checkbox.checked && checkbox !== checkboxClickTarget) {
                  checkbox.click()
                  await sleep(60)
                }
                if (checkbox.checked) {
                  return true
                }
                await sleep(intervalMs)
                continue
              }

              if (typeof target.scrollIntoView === 'function') {
                target.scrollIntoView({ block: 'nearest', inline: 'nearest' })
              }
              if (typeof target.click === 'function') {
                target.click()
              } else {
                target.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
              }
              return true
            }

            if (scrollAttempts < maxScrollAttempts) {
              const moved = scrollVisibleContainers()
              scrollAttempts += 1
              await sleep(moved ? intervalMs : Math.max(intervalMs, 120))
              continue
            }

            await sleep(intervalMs)
          }
          return false
        })()
      })()`,
      true
    )

    if (!clicked) {
      throw new Error(`clickByText 失败：selector=${selector}, text=${text}`)
    }
  }

  public async fillSelector(
    selector: string,
    value: string,
    options?: { clearBeforeFill?: boolean; timeoutMs?: number; intervalMs?: number }
  ): Promise<void> {
    const wc = this.tkWCV?.webContents
    if (!wc || wc.isDestroyed()) {
      throw new Error('WebContents 不可用，无法执行 fillSelector')
    }

    const clearBeforeFill = Boolean(options?.clearBeforeFill ?? true)
    const timeoutMs = Math.max(1000, Number(options?.timeoutMs ?? 10000))
    const intervalMs = Math.max(50, Number(options?.intervalMs ?? 250))

    const filled = await wc.executeJavaScript(
      `(() => {
        const selector = ${JSON.stringify(selector)}
        const nextValue = ${JSON.stringify(value)}
        const clearBeforeFill = ${JSON.stringify(clearBeforeFill)}
        const timeoutMs = ${JSON.stringify(timeoutMs)}
        const intervalMs = ${JSON.stringify(intervalMs)}

        const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
        const isVisible = (element) => {
          if (!(element instanceof HTMLElement)) return false
          const style = window.getComputedStyle(element)
          if (style.display === 'none' || style.visibility === 'hidden') return false
          return element.offsetParent !== null || style.position === 'fixed'
        }

        const assignValue = (element, value) => {
          const prototype = Object.getPrototypeOf(element)
          const descriptor = prototype ? Object.getOwnPropertyDescriptor(prototype, 'value') : null
          const nativeSetter = descriptor && descriptor.set
          if (nativeSetter) {
            nativeSetter.call(element, value)
          } else {
            element.value = value
          }
        }

        const triggerEvents = (element, nextValue) => {
          element.dispatchEvent(new Event('focus', { bubbles: true }))
          try {
            element.dispatchEvent(new InputEvent('input', { bubbles: true, data: nextValue, inputType: 'insertText' }))
          } catch (error) {
            element.dispatchEvent(new Event('input', { bubbles: true }))
          }
          element.dispatchEvent(new Event('change', { bubbles: true }))
        }

        return (async () => {
          const startedAt = Date.now()
          while (Date.now() - startedAt < timeoutMs) {
            const node =
              Array.from(document.querySelectorAll(selector)).find(
                (candidate) =>
                  isVisible(candidate) &&
                  (candidate instanceof HTMLInputElement || candidate instanceof HTMLTextAreaElement)
              ) || null

            if (node instanceof HTMLInputElement || node instanceof HTMLTextAreaElement) {
              node.focus()
              if (clearBeforeFill) {
                assignValue(node, '')
              }
              assignValue(node, nextValue)
              if (typeof node.setSelectionRange === 'function') {
                const cursor = String(nextValue).length
                node.setSelectionRange(cursor, cursor)
              }
              triggerEvents(node, nextValue)
              return true
            }
            await sleep(intervalMs)
          }
          return false
        })()
      })()`,
      true
    )

    if (!filled) {
      throw new Error(`fillSelector 失败：未找到可填值元素 ${selector}`)
    }
  }

  public async setCheckbox(
    selector: string,
    options?: {
      checked?: boolean
      timeoutMs?: number
      intervalMs?: number
      scrollContainerSelector?: string
      scrollStepPx?: number
      maxScrollAttempts?: number
    }
  ): Promise<void> {
    const wc = this.tkWCV?.webContents
    if (!wc || wc.isDestroyed()) {
      throw new Error('WebContents 不可用，无法执行 setCheckbox')
    }

    const checked = Boolean(options?.checked ?? true)
    const timeoutMs = Math.max(1000, Number(options?.timeoutMs ?? 10000))
    const intervalMs = Math.max(50, Number(options?.intervalMs ?? 250))
    const scrollContainerSelector = String(options?.scrollContainerSelector || '')
    const scrollStepPx = Math.max(40, Number(options?.scrollStepPx ?? 320))
    const maxScrollAttempts = Math.max(0, Number(options?.maxScrollAttempts ?? 0))

    const updated = await wc.executeJavaScript(
      `(() => {
        const selector = ${JSON.stringify(selector)}
        const expectedChecked = ${JSON.stringify(checked)}
        const timeoutMs = ${JSON.stringify(timeoutMs)}
        const intervalMs = ${JSON.stringify(intervalMs)}
        const scrollContainerSelector = ${JSON.stringify(scrollContainerSelector)}
        const scrollStepPx = ${JSON.stringify(scrollStepPx)}
        const maxScrollAttempts = ${JSON.stringify(maxScrollAttempts)}

        const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
        const isVisible = (element) => {
          if (!(element instanceof HTMLElement)) return false
          const style = window.getComputedStyle(element)
          if (style.display === 'none' || style.visibility === 'hidden') return false
          return element.offsetParent !== null || style.position === 'fixed'
        }
        const resolveCheckbox = (root) => {
          if (!root) return null
          if (root instanceof HTMLInputElement && root.type === 'checkbox') return root
          if (!(root instanceof Element)) return null
          return root.querySelector('input[type="checkbox"]')
        }
        const resolveClickTarget = (root, input) => {
          if (root instanceof HTMLLabelElement) return root
          if (root instanceof HTMLInputElement) {
            return root.closest('label') || root.parentElement || root
          }
          if (input?.closest('label')) return input.closest('label')
          return input || root
        }
        const findCandidate = () => {
          const candidates = Array.from(document.querySelectorAll(selector))
          for (const candidate of candidates) {
            const input = resolveCheckbox(candidate)
            if (!(input instanceof HTMLInputElement)) continue
            const clickTarget = resolveClickTarget(candidate, input)
            if (
              isVisible(candidate) ||
              (clickTarget instanceof HTMLElement && isVisible(clickTarget)) ||
              (input instanceof HTMLElement && isVisible(input))
            ) {
              return { root: candidate, input, clickTarget }
            }
          }
          return null
        }
        const scrollVisibleContainers = () => {
          if (!scrollContainerSelector) return false
          const containers = Array.from(document.querySelectorAll(scrollContainerSelector)).filter((node) => isVisible(node))
          let moved = false
          for (const container of containers) {
            if (!(container instanceof HTMLElement)) continue
            const previousTop = container.scrollTop
            const nextTop = Math.min(previousTop + scrollStepPx, Math.max(0, container.scrollHeight - container.clientHeight))
            if (nextTop !== previousTop) {
              container.scrollTop = nextTop
              container.dispatchEvent(new Event('scroll', { bubbles: true }))
              moved = true
            }
          }
          return moved
        }

        return (async () => {
          const startedAt = Date.now()
          let scrollAttempts = 0
          while (Date.now() - startedAt < timeoutMs) {
            const candidate = findCandidate()
            if (!candidate) {
              if (scrollAttempts < maxScrollAttempts) {
                const moved = scrollVisibleContainers()
                scrollAttempts += 1
                await sleep(moved ? intervalMs : Math.max(intervalMs, 120))
                continue
              }
              await sleep(intervalMs)
              continue
            }

            const root = candidate.root
            const input = candidate.input

            if (input.checked === expectedChecked) {
              return true
            }

            const target = candidate.clickTarget
            if (typeof target?.scrollIntoView === 'function') {
              target.scrollIntoView({ block: 'nearest', inline: 'nearest' })
            }
            if (typeof target?.click === 'function') {
              target.click()
            } else {
              target?.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
            }

            await sleep(Math.max(intervalMs, 80))
            if (input.checked === expectedChecked) {
              return true
            }
          }

          return false
        })()
      })()`,
      true
    )

    if (!updated) {
      throw new Error(`setCheckbox 失败：selector=${selector}, checked=${String(checked)}`)
    }
  }

  public async pressKey(key: string, options?: { native?: boolean }): Promise<void> {
    const wc = this.tkWCV?.webContents
    if (!wc || wc.isDestroyed()) {
      throw new Error('WebContents 不可用，无法执行 pressKey')
    }

    if (options?.native) {
      wc.focus()
      wc.sendInputEvent({ type: 'keyDown', keyCode: key })
      if (key.length === 1) {
        wc.sendInputEvent({ type: 'char', keyCode: key })
      }
      wc.sendInputEvent({ type: 'keyUp', keyCode: key })
      return
    }

    await wc.executeJavaScript(
      `(() => {
        const key = ${JSON.stringify(key)}
        const eventOptions = { key, code: key, bubbles: true, cancelable: true }
        const target =
          document.activeElement instanceof HTMLElement
            ? document.activeElement
            : document.body || document.documentElement || document

        if (target instanceof HTMLElement && typeof target.focus === 'function') {
          target.focus()
        }

        target.dispatchEvent(new KeyboardEvent('keydown', eventOptions))
        target.dispatchEvent(new KeyboardEvent('keypress', eventOptions))
        target.dispatchEvent(new KeyboardEvent('keyup', eventOptions))
      })()`,
      true
    )
  }

  public async getCurrentUrl(): Promise<string> {
    const wc = this.tkWCV?.webContents
    if (!wc || wc.isDestroyed()) {
      return ''
    }
    try {
      return String(await wc.executeJavaScript('location.href'))
    } catch {
      return ''
    }
  }

  public async selectTab(
    label: string,
    options?: { tabSelector?: string; labelSelector?: string; timeoutMs?: number; intervalMs?: number }
  ): Promise<boolean> {
    const wc = this.tkWCV?.webContents
    if (!wc || wc.isDestroyed()) {
      return false
    }

    const tabSelector = String(options?.tabSelector || '[role="tab"], .arco-tabs-header-title')
    const labelSelector = String(options?.labelSelector || '.m4b-tabs-pane-title-content')
    const timeoutMs = Math.max(1000, Number(options?.timeoutMs ?? 10000))
    const intervalMs = Math.max(50, Number(options?.intervalMs ?? 250))

    const ok = await wc.executeJavaScript(
      `(() => {
        const targetLabel = ${JSON.stringify(label)}
        const tabSelector = ${JSON.stringify(tabSelector)}
        const labelSelector = ${JSON.stringify(labelSelector)}
        const timeoutMs = ${JSON.stringify(timeoutMs)}
        const intervalMs = ${JSON.stringify(intervalMs)}

        const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
        const normalize = (value) => String(value ?? '').replace(/\\s+/g, ' ').trim().toLowerCase()
        const expected = normalize(targetLabel)

        const getTabLabel = (node) => {
          const viaLabelSelector = node.querySelector(labelSelector)
          if (viaLabelSelector) return normalize(viaLabelSelector.textContent)
          return normalize(node.textContent)
        }

        const isSelected = (node) =>
          node.getAttribute('aria-selected') === 'true' ||
          String(node.getAttribute('class') || '').includes('arco-tabs-header-title-active')

        const findTarget = () => {
          const tabs = Array.from(document.querySelectorAll(tabSelector))
          return tabs.find((node) => getTabLabel(node) === expected) || null
        }

        return (async () => {
          const startedAt = Date.now()
          while (Date.now() - startedAt < timeoutMs) {
            const target = findTarget()
            if (!target) {
              await sleep(intervalMs)
              continue
            }

            if (!isSelected(target)) {
              if (typeof target.click === 'function') {
                target.click()
              } else {
                target.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
              }
            }

            if (isSelected(target)) return true
            await sleep(intervalMs)
          }
          return false
        })()
      })()`,
      true
    )

    return Boolean(ok)
  }

  public async waitForElementCount(
    selector: string,
    options?: { minCount?: number; timeoutMs?: number; intervalMs?: number }
  ): Promise<number> {
    const wc = this.tkWCV?.webContents
    if (!wc || wc.isDestroyed()) {
      return 0
    }

    const minCount = Math.max(0, Number(options?.minCount ?? 1))
    const timeoutMs = Math.max(1000, Number(options?.timeoutMs ?? 10000))
    const intervalMs = Math.max(50, Number(options?.intervalMs ?? 250))

    const count = await wc.executeJavaScript(
      `(() => {
        const selector = ${JSON.stringify(selector)}
        const minCount = ${JSON.stringify(minCount)}
        const timeoutMs = ${JSON.stringify(timeoutMs)}
        const intervalMs = ${JSON.stringify(intervalMs)}

        const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))

        return (async () => {
          const startedAt = Date.now()
          while (Date.now() - startedAt < timeoutMs) {
            const count = document.querySelectorAll(selector).length
            if (count >= minCount) return count
            await sleep(intervalMs)
          }
          return document.querySelectorAll(selector).length
        })()
      })()`,
      true
    )

    const parsed = Number(count)
    return Number.isFinite(parsed) ? parsed : 0
  }

  public async clickPaginationNext(options?: {
    nextSelector?: string
    disabledClassContains?: string
    timeoutMs?: number
    intervalMs?: number
  }): Promise<BrowserPaginationResult> {
    const wc = this.tkWCV?.webContents
    if (!wc || wc.isDestroyed()) {
      return 'no_more_pages'
    }

    const nextSelector = String(options?.nextSelector || 'li.arco-pagination-item-next')
    const disabledClassContains = String(options?.disabledClassContains || 'arco-pagination-item-disabled')
    const timeoutMs = Math.max(1000, Number(options?.timeoutMs ?? 8000))
    const intervalMs = Math.max(50, Number(options?.intervalMs ?? 200))

    const result = await wc.executeJavaScript(
      `(() => {
        const nextSelector = ${JSON.stringify(nextSelector)}
        const disabledClassContains = ${JSON.stringify(disabledClassContains)}
        const timeoutMs = ${JSON.stringify(timeoutMs)}
        const intervalMs = ${JSON.stringify(intervalMs)}

        const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
        const getNextButton = () => document.querySelector(nextSelector)
        const isDisabled = (node) =>
          !node ||
          node.getAttribute('aria-disabled') === 'true' ||
          String(node.getAttribute('class') || '').includes(disabledClassContains)

        return (async () => {
          const startedAt = Date.now()
          while (Date.now() - startedAt < timeoutMs) {
            const nextButton = getNextButton()
            if (isDisabled(nextButton)) return 'no_more_pages'

            if (typeof nextButton.click === 'function') {
              nextButton.click()
            } else {
              nextButton.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
            }
            await sleep(intervalMs)
            return 'moved'
          }
          return 'no_more_pages'
        })()
      })()`,
      true
    )

    return result === 'moved' ? 'moved' : 'no_more_pages'
  }

  public async closeDrawer(options?: {
    drawerSelector?: string
    closeSelector?: string
    timeoutMs?: number
    intervalMs?: number
  }): Promise<boolean> {
    const wc = this.tkWCV?.webContents
    if (!wc || wc.isDestroyed()) {
      return false
    }

    const drawerSelector = String(options?.drawerSelector || '.arco-drawer-content-wrapper, .arco-drawer')
    const closeSelector = String(options?.closeSelector || '.arco-drawer-close-icon, [class*="drawer-close-icon"]')
    const timeoutMs = Math.max(1000, Number(options?.timeoutMs ?? 6000))
    const intervalMs = Math.max(50, Number(options?.intervalMs ?? 120))

    const closed = await wc.executeJavaScript(
      `(() => {
        const drawerSelector = ${JSON.stringify(drawerSelector)}
        const closeSelector = ${JSON.stringify(closeSelector)}
        const timeoutMs = ${JSON.stringify(timeoutMs)}
        const intervalMs = ${JSON.stringify(intervalMs)}

        const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
        const isVisible = (element) => {
          if (!(element instanceof HTMLElement)) return false
          const style = window.getComputedStyle(element)
          if (style.display === 'none' || style.visibility === 'hidden') return false
          return element.offsetParent !== null || style.position === 'fixed'
        }

        const getActiveDrawer = () => {
          const candidates = Array.from(document.querySelectorAll(drawerSelector)).filter((node) => isVisible(node))
          return candidates.length ? candidates[candidates.length - 1] : null
        }

        const waitDrawerGone = async () => {
          const startedAt = Date.now()
          while (Date.now() - startedAt < timeoutMs) {
            if (!getActiveDrawer()) return true
            await sleep(intervalMs)
          }
          return !getActiveDrawer()
        }

        return (async () => {
          const drawer = getActiveDrawer()
          if (!drawer) return true

          const closeBtn = drawer.querySelector(closeSelector)
          if (closeBtn) {
            if (typeof closeBtn.click === 'function') {
              closeBtn.click()
            } else {
              closeBtn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
            }
          } else {
            document.dispatchEvent(
              new KeyboardEvent('keydown', {
                key: 'Escape',
                code: 'Escape',
                keyCode: 27,
                which: 27,
                bubbles: true
              })
            )
          }

          const closed = await waitDrawerGone()
          if (closed) return true

          // 再尝试一次 Esc，提升稳定性。
          document.dispatchEvent(
            new KeyboardEvent('keydown', {
              key: 'Escape',
              code: 'Escape',
              keyCode: 27,
              which: 27,
              bubbles: true
            })
          )
          return waitDrawerGone()
        })()
      })()`,
      true
    )

    return Boolean(closed)
  }

  public async startJsonResponseCapture(options: {
    captureKey: string
    urlIncludes: string
    method?: string
    reset?: boolean
  }): Promise<void> {
    const wc = this.tkWCV?.webContents
    if (!wc || wc.isDestroyed()) {
      throw new Error('WebContents 不可用，无法启动 JSON 响应捕获')
    }

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
      await this.disposeJsonResponseCaptureSession(captureKey)
    }

    await this.ensureNetworkDebuggerReady(wc)

    const session: JsonResponseCaptureSession = {
      captureKey,
      urlIncludes,
      requestMethod: requestMethod || undefined,
      responses: [],
      matchedRequestIds: new Set<string>(),
      processedRequestIds: new Set<string>(),
      pendingTasks: new Set<Promise<void>>(),
      reachedEndByApi: false,
      listener: (_event, method, params) => {
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
            const responseBody = (await wc.debugger.sendCommand('Network.getResponseBody', {
              requestId
            })) as { body?: string; base64Encoded?: boolean }

            const rawBody = responseBody.base64Encoded
              ? Buffer.from(String(responseBody.body || ''), 'base64').toString('utf8')
              : String(responseBody.body || '')
            if (!rawBody) return

            const parsedBody = JSON.parse(rawBody)
            session.responses.push(parsedBody)

            const hasMore = this.readHasMoreFlag(parsedBody)
            if (hasMore === false) {
              session.reachedEndByApi = true
            }
          } catch (error) {
            logger.warn(`JSON 响应捕获失败: ${(error as Error)?.message || error}`)
          }
        })()

        session.pendingTasks.add(task)
        void task.finally(() => {
          session.pendingTasks.delete(task)
        })
      }
    }

    wc.debugger.on('message', session.listener)
    this.jsonResponseCaptures.set(captureKey, session)
    logger.info(
      `启动 JSON 响应捕获: key=${captureKey} urlIncludes=${urlIncludes}${session.requestMethod ? ` method=${session.requestMethod}` : ''}`
    )
  }

  public async collectJsonResponsesByScrolling(options: {
    captureKey: string
    initialWaitMs?: number
    scrollContainerSelector?: string
    scrollStepPx?: number
    scrollIntervalMs?: number
    settleWaitMs?: number
    maxIdleRounds?: number
    maxScrollRounds?: number
  }): Promise<unknown[]> {
    const captureKey = String(options.captureKey || '').trim()
    const session = this.jsonResponseCaptures.get(captureKey)
    if (!session) {
      throw new Error(`未找到 JSON 响应捕获会话: ${captureKey}`)
    }

    const initialWaitMs = Math.max(0, Number(options.initialWaitMs ?? 0))
    const scrollIntervalMs = Math.max(120, Number(options.scrollIntervalMs ?? 1200))
    const settleWaitMs = Math.max(120, Number(options.settleWaitMs ?? 1500))
    const maxIdleRounds = Math.max(1, Number(options.maxIdleRounds ?? 4))
    const maxScrollRounds = Math.max(1, Number(options.maxScrollRounds ?? 200))

    if (initialWaitMs > 0) {
      await this.waitForDelay(initialWaitMs)
    }

    let previousResponseCount = session.responses.length
    let noNewResponseRounds = 0

    for (let round = 0; round < maxScrollRounds; round += 1) {
      if (session.reachedEndByApi) {
        break
      }

      await this.scrollPageByStep({
        containerSelector: options.scrollContainerSelector,
        stepPx: options.scrollStepPx
      })
      await this.waitForDelay(scrollIntervalMs)

      const nextResponseCount = session.responses.length
      const hasNewResponses = nextResponseCount > previousResponseCount
      previousResponseCount = nextResponseCount

      if (hasNewResponses) {
        noNewResponseRounds = 0
      } else {
        noNewResponseRounds += 1
      }

      if (session.reachedEndByApi || noNewResponseRounds >= maxIdleRounds) {
        break
      }
    }

    let settledResponseCount = session.responses.length
    let settleRounds = 0
    while (settleRounds < 2) {
      await this.waitForDelay(settleWaitMs)
      const currentResponseCount = session.responses.length
      if (currentResponseCount === settledResponseCount) {
        settleRounds += 1
      } else {
        settledResponseCount = currentResponseCount
        settleRounds = 0
      }
    }

    const reachedEndByApi = session.reachedEndByApi
    const responses = await this.disposeJsonResponseCaptureSession(captureKey)
    logger.info(`完成 JSON 响应采集: key=${captureKey} responses=${responses.length} api_end=${reachedEndByApi}`)
    return responses
  }

  public async readText(
    selector: string,
    options?: {
      timeoutMs?: number
      intervalMs?: number
      trim?: boolean
      preserveLineBreaks?: boolean
      pick?: 'first' | 'last'
      visibleOnly?: boolean
    }
  ): Promise<string> {
    const wc = this.tkWCV?.webContents
    if (!wc || wc.isDestroyed()) {
      return ''
    }

    const timeoutMs = Math.max(1000, Number(options?.timeoutMs ?? 10000))
    const intervalMs = Math.max(50, Number(options?.intervalMs ?? 250))
    const trim = Boolean(options?.trim ?? true)
    const preserveLineBreaks = Boolean(options?.preserveLineBreaks ?? false)
    const pick = options?.pick === 'last' ? 'last' : 'first'
    const visibleOnly = Boolean(options?.visibleOnly ?? false)

    const text = await wc.executeJavaScript(
      `(() => {
        const selector = ${JSON.stringify(selector)}
        const timeoutMs = ${JSON.stringify(timeoutMs)}
        const intervalMs = ${JSON.stringify(intervalMs)}
        const trim = ${JSON.stringify(trim)}
        const preserveLineBreaks = ${JSON.stringify(preserveLineBreaks)}
        const pick = ${JSON.stringify(pick)}
        const visibleOnly = ${JSON.stringify(visibleOnly)}

        const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
        const isVisible = (element) => {
          if (!(element instanceof HTMLElement)) return false
          const style = window.getComputedStyle(element)
          if (style.display === 'none' || style.visibility === 'hidden') return false
          return element.offsetParent !== null || style.position === 'fixed'
        }
        const normalize = (value) => {
          const source = String(value ?? '').replace(/\\u00a0/g, ' ').replace(/\\r\\n/g, '\\n')
          if (preserveLineBreaks) {
            return source
              .split('\\n')
              .map((line) => line.replace(/[\\t ]+/g, ' ').trimEnd())
              .join('\\n')
          }
          return source.replace(/\\s+/g, ' ')
        }

        return (async () => {
          const startedAt = Date.now()
          while (Date.now() - startedAt < timeoutMs) {
            const candidates = Array.from(document.querySelectorAll(selector))
            const nodes = visibleOnly ? candidates.filter((node) => isVisible(node)) : candidates
            const node = pick === 'last' ? nodes[nodes.length - 1] : nodes[0]
            const rawValue = preserveLineBreaks ? node?.innerText || node?.textContent || '' : node?.textContent || ''
            const value = normalize(rawValue)
            const normalized = trim ? value.trim() : value
            if (normalized) return normalized
            await sleep(intervalMs)
          }
          return ''
        })()
      })()`,
      true
    )

    return String(text ?? '')
  }

  public async waitForDelay(ms: number): Promise<void> {
    await this.sleep(ms)
  }

  private async ensureNetworkDebuggerReady(wc: Electron.WebContents): Promise<void> {
    if (!wc.debugger.isAttached()) {
      wc.debugger.attach('1.3')
    }
    await wc.debugger.sendCommand('Network.enable')
  }

  private async disposeJsonResponseCaptureSession(captureKey: string): Promise<unknown[]> {
    const session = this.jsonResponseCaptures.get(captureKey)
    if (!session) return []

    const wc = this.tkWCV?.webContents
    if (wc && !wc.isDestroyed() && wc.debugger.isAttached()) {
      wc.debugger.off('message', session.listener)
    }

    await Promise.allSettled(Array.from(session.pendingTasks))
    this.jsonResponseCaptures.delete(captureKey)
    return session.responses
  }

  private readHasMoreFlag(payload: unknown): boolean | undefined {
    if (!payload || typeof payload !== 'object') {
      return undefined
    }

    const record = payload as Record<string, unknown>
    const nextPagination = record.next_pagination
    if (nextPagination && typeof nextPagination === 'object') {
      const value = (nextPagination as Record<string, unknown>).has_more
      if (typeof value === 'boolean') {
        return value
      }
    }

    const pagination = record.pagination
    if (pagination && typeof pagination === 'object') {
      const value = (pagination as Record<string, unknown>).has_more
      if (typeof value === 'boolean') {
        return value
      }
    }

    if (typeof record.has_more === 'boolean') {
      return record.has_more
    }

    return undefined
  }

  private async scrollPageByStep(options?: { containerSelector?: string; stepPx?: number }): Promise<ScrollProgressResult> {
    const wc = this.tkWCV?.webContents
    if (!wc || wc.isDestroyed()) {
      return { moved: false, reachedEnd: true, scrollTop: 0, maxScrollTop: 0 }
    }

    const containerSelector = String(options?.containerSelector || '')
    const stepPx = Math.max(200, Number(options?.stepPx ?? 1200))

    const result = await wc.executeJavaScript(
      `(() => {
        const containerSelector = ${JSON.stringify(containerSelector)}
        const stepPx = ${JSON.stringify(stepPx)}

        const isVisible = (element) => {
          if (!(element instanceof HTMLElement)) return false
          const style = window.getComputedStyle(element)
          if (style.display === 'none' || style.visibility === 'hidden') return false
          return element.offsetParent !== null || style.position === 'fixed'
        }

        const isScrollable = (element) => {
          if (!(element instanceof HTMLElement)) return false
          return element.scrollHeight - element.clientHeight > 16
        }

        const pickTarget = () => {
          if (containerSelector) {
            const explicit = Array.from(document.querySelectorAll(containerSelector)).find(
              (element) => isVisible(element) && isScrollable(element)
            )
            if (explicit instanceof HTMLElement) return explicit
          }

          const docScroller =
            document.scrollingElement instanceof HTMLElement
              ? document.scrollingElement
              : document.documentElement instanceof HTMLElement
                ? document.documentElement
                : null
          if (docScroller && docScroller.scrollHeight - window.innerHeight > 16) {
            return docScroller
          }

          const fallback = Array.from(document.querySelectorAll('*'))
            .filter((element) => isVisible(element) && isScrollable(element))
            .sort((left, right) => right.scrollHeight - left.scrollHeight)[0]
          return fallback instanceof HTMLElement ? fallback : null
        }

        const target = pickTarget()
        if (!target) {
          return { moved: false, reachedEnd: true, scrollTop: 0, maxScrollTop: 0 }
        }

        const isDocumentScroller =
          target === document.scrollingElement || target === document.documentElement || target === document.body
        const previousTop = isDocumentScroller ? window.scrollY : target.scrollTop
        const maxScrollTop = Math.max(0, target.scrollHeight - (isDocumentScroller ? window.innerHeight : target.clientHeight))
        const nextTop = containerSelector ? maxScrollTop : Math.min(previousTop + stepPx, maxScrollTop)

        if (isDocumentScroller) {
          window.scrollTo(0, nextTop)
          document.dispatchEvent(new Event('scroll', { bubbles: true }))
        } else {
          target.scrollTop = nextTop
          target.dispatchEvent(new Event('scroll', { bubbles: true }))
        }

        return {
          moved: nextTop !== previousTop,
          reachedEnd: nextTop >= maxScrollTop,
          scrollTop: nextTop,
          maxScrollTop
        }
      })()`,
      true
    )

    const current = (result || {}) as Partial<ScrollProgressResult>
    return {
      moved: Boolean(current.moved),
      reachedEnd: Boolean(current.reachedEnd),
      scrollTop: Number(current.scrollTop ?? 0),
      maxScrollTop: Number(current.maxScrollTop ?? 0)
    }
  }

  private extractShopRegion(url: string): string | null {
    try {
      const current = new URL(url)
      const region = current.searchParams.get('shop_region')
      if (region) return region.toUpperCase()
    } catch {
      /* empty */
    }

    const hostMatch = url.match(/seller-([a-z]{2})\./i)
    if (hostMatch?.[1]) return hostMatch[1].toUpperCase()

    return null
  }

  private async waitUntilBodyContainsText(text: string, timeoutMs: number, intervalMs: number): Promise<boolean> {
    const expected = String(text || '').trim().toLowerCase()
    if (!expected) return false

    const wc = this.tkWCV?.webContents
    if (!wc || wc.isDestroyed()) {
      return false
    }

    const startedAt = Date.now()
    while (Date.now() - startedAt < timeoutMs) {
      try {
        const hasText = Boolean(
          await wc.executeJavaScript(
            `(() => {
              const bodyText = String(document?.body?.innerText || '').toLowerCase()
              return bodyText.includes(${JSON.stringify(expected)})
            })()`
          )
        )
        if (hasText) {
          return true
        }
      } catch {
        // 页面切换过程中 executeJavaScript 可能短暂失败，继续轮询即可。
      }
      await this.sleep(intervalMs)
    }

    return false
  }

  private async sleep(ms: number): Promise<void> {
    await new Promise((resolve) => setTimeout(resolve, ms))
  }

  public getWebContentsView(): WebContentsView {
    return this.tkWCV!
  }

  public resize(): void {
    const [contentWidth, contentHeight] = this.baseWindow!.getContentSize()

    this.tkWCV!.setBounds({
      x: 0,
      y: 120,
      width: contentWidth,
      height: contentHeight - 120
    })

    if (!this.tkWCV!.getVisible()) {
      this.tkWCV!.setVisible(true)
    }
  }
}
