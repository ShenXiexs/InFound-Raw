import type { Locator, Page } from 'playwright'
import type { TaskLoggerLike } from '../task-dsl/types'
import type { BrowserSelectorState } from '../task-dsl/browser-actions'
import type { BrowserActionTarget } from '../task-dsl/browser-action-runner'
import { PlaywrightJsonResponseCaptureManager } from './playwright-response-capture'
import { sleep } from './shared'

const normalizeText = (value: string, caseSensitive: boolean): string => {
  const text = String(value || '').replace(/\s+/g, ' ').trim()
  return caseSensitive ? text : text.toLowerCase()
}

export class PlaywrightBrowserActionTarget implements BrowserActionTarget {
  constructor(
    private readonly page: Page,
    _logger: TaskLoggerLike,
    private readonly captureManager: PlaywrightJsonResponseCaptureManager
  ) {}

  public async openView(url: string | null): Promise<void> {
    const targetUrl = String(url || '').trim()
    if (!targetUrl) {
      throw new Error('打开页面失败: url 为空')
    }

    await this.page.goto(targetUrl, {
      waitUntil: 'domcontentloaded'
    })
    await this.page.waitForLoadState('domcontentloaded')
  }

  public async waitForDelay(ms: number): Promise<void> {
    await this.page.waitForTimeout(Math.max(0, Number(ms || 0)))
  }

  public async waitForBodyText(text: string, timeoutMs = 10000, intervalMs = 250): Promise<boolean> {
    const expected = String(text || '').trim()
    const deadline = Date.now() + Math.max(0, Number(timeoutMs || 0))

    while (Date.now() < deadline) {
      const bodyText = await this.page.locator('body').textContent().catch(() => '')
      if (String(bodyText || '').includes(expected)) {
        return true
      }
      await sleep(Math.max(50, Number(intervalMs || 250)))
    }

    return false
  }

  public async waitForSelector(
    selector: string,
    options?: { state?: BrowserSelectorState; timeoutMs?: number; intervalMs?: number }
  ): Promise<boolean> {
    const state = options?.state ?? 'present'
    const timeoutMs = Math.max(0, Number(options?.timeoutMs ?? 10000))
    const mappedState = state === 'present' ? 'attached' : state === 'absent' ? 'detached' : state

    try {
      await this.page.waitForSelector(selector, {
        state: mappedState,
        timeout: timeoutMs
      })
      return true
    } catch {
      return false
    }
  }

  public async clickSelector(selector: string, options?: { native?: boolean }): Promise<void> {
    const locator = await this.resolveBestLocator(selector)
    if (options?.native) {
      await locator.click({ force: true })
      return
    }

    await locator.click()
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
    const expected = String(text || '').trim()
    const exact = options.exact ?? true
    const caseSensitive = options.caseSensitive ?? false
    const timeoutMs = Math.max(0, Number(options.timeoutMs ?? 10000))
    const intervalMs = Math.max(50, Number(options.intervalMs ?? 250))
    const maxScrollAttempts = Math.max(0, Number(options.maxScrollAttempts ?? 0))
    const deadline = Date.now() + timeoutMs
    let scrollAttempts = 0

    while (Date.now() < deadline) {
      const locator = this.page.locator(options.selector)
      const count = await locator.count()

      for (let index = 0; index < count; index += 1) {
        const current = locator.nth(index)
        const currentText = await current.innerText().catch(async () => String((await current.textContent().catch(() => '')) || ''))
        const normalizedCurrent = normalizeText(currentText, caseSensitive)
        const normalizedExpected = normalizeText(expected, caseSensitive)
        const matched = exact ? normalizedCurrent === normalizedExpected : normalizedCurrent.includes(normalizedExpected)
        if (!matched) continue

        await current.scrollIntoViewIfNeeded().catch(() => {})
        await current.click().catch(async () => {
          await current.click({ force: true })
        })
        return
      }

      const canScroll =
        options.scrollContainerSelector &&
        scrollAttempts < maxScrollAttempts &&
        (await this.scrollContainerOnce(options.scrollContainerSelector, options.scrollStepPx))
      if (canScroll) {
        scrollAttempts += 1
        await sleep(intervalMs)
        continue
      }

      await sleep(intervalMs)
    }

    throw new Error(`未找到目标文本并点击: text=${expected}`)
  }

  public async fillSelector(
    selector: string,
    value: string,
    options?: { clearBeforeFill?: boolean; timeoutMs?: number; intervalMs?: number }
  ): Promise<void> {
    const locator = await this.resolveBestLocator(selector)
    await locator.scrollIntoViewIfNeeded().catch(() => {})
    await locator.click({ force: true }).catch(() => {})

    if (options?.clearBeforeFill === false) {
      await this.page.keyboard.type(String(value))
      return
    }

    await locator.fill(String(value))
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
    const desiredChecked = options?.checked ?? true
    const timeoutMs = Math.max(0, Number(options?.timeoutMs ?? 10000))
    const intervalMs = Math.max(50, Number(options?.intervalMs ?? 250))
    const maxScrollAttempts = Math.max(0, Number(options?.maxScrollAttempts ?? 0))
    const deadline = Date.now() + timeoutMs
    let scrollAttempts = 0

    while (Date.now() < deadline) {
      const locator = this.page.locator(selector)
      const count = await locator.count()

      for (let index = 0; index < count; index += 1) {
        const current = locator.nth(index)
        const exists = await current.count().catch(() => 0)
        if (!exists) continue
        const nestedInput = current.locator('input[type="checkbox"]').first()
        const hasNestedInput = (await nestedInput.count().catch(() => 0)) > 0

        const readCheckedState = async (): Promise<boolean> => {
          if (hasNestedInput) {
            return nestedInput.isChecked().catch(() => false)
          }
          return current
            .evaluate((node) => {
              if (node instanceof HTMLInputElement) {
                return Boolean(node.checked)
              }
              const container = node as HTMLElement
              const input = container.querySelector('input[type="checkbox"]') as HTMLInputElement | null
              if (input) {
                return Boolean(input.checked)
              }
              return Boolean(container.getAttribute('aria-checked') === 'true')
            })
            .catch(() => false)
        }

        const currentChecked = await readCheckedState()

        if (currentChecked === desiredChecked) {
          return
        }

        await current.scrollIntoViewIfNeeded().catch(() => {})

        try {
          if (hasNestedInput) {
            await nestedInput.setChecked(desiredChecked, { force: true })
          } else if (desiredChecked) {
            await current.check({ force: true })
          } else {
            await current.uncheck({ force: true })
          }
        } catch {
          await current.evaluate((node, checked) => {
            const target = node as HTMLElement
            const input = target instanceof HTMLInputElement ? target : (target.querySelector('input[type="checkbox"]') as HTMLInputElement | null)
            if (input) {
              if (Boolean(input.checked) !== checked) {
                input.click()
              }
              return
            }
            const label = target.closest('label') as HTMLElement | null
            if (label) {
              label.click()
              return
            }
            target.click()
          }, desiredChecked)
        }

        const verified = await readCheckedState()

        if (verified === desiredChecked) {
          return
        }
      }

      const canScroll =
        options?.scrollContainerSelector &&
        scrollAttempts < maxScrollAttempts &&
        (await this.scrollContainerOnce(options.scrollContainerSelector, options.scrollStepPx))
      if (canScroll) {
        scrollAttempts += 1
        await sleep(intervalMs)
        continue
      }

      await sleep(intervalMs)
    }

    throw new Error(`设置复选框失败: selector=${selector} checked=${String(desiredChecked)}`)
  }

  public async pressKey(key: string, _options?: { native?: boolean }): Promise<void> {
    await this.page.keyboard.press(key)
  }

  public async getCurrentUrl(): Promise<string> {
    return this.page.url()
  }

  public async startJsonResponseCapture(options: {
    captureKey: string
    urlIncludes: string
    method?: string
    reset?: boolean
  }): Promise<void> {
    await this.captureManager.startJsonResponseCapture(this.page, options)
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
    if (!captureKey) {
      throw new Error('captureKey 不能为空')
    }

    const initialWaitMs = Math.max(0, Number(options.initialWaitMs ?? 1500))
    const scrollIntervalMs = Math.max(50, Number(options.scrollIntervalMs ?? 1200))
    const settleWaitMs = Math.max(50, Number(options.settleWaitMs ?? 1500))
    const maxIdleRounds = Math.max(1, Number(options.maxIdleRounds ?? 3))
    const maxScrollRounds = Math.max(1, Number(options.maxScrollRounds ?? 80))

    if (initialWaitMs > 0) {
      await sleep(initialWaitMs)
    }

    let lastResponseCount = this.captureManager.getResponses(captureKey).length
    let idleRounds = 0

    for (let round = 0; round < maxScrollRounds; round += 1) {
      if (this.captureManager.hasReachedEndByApi(captureKey)) {
        break
      }

      const moved = await this.scrollContainerOnce(options.scrollContainerSelector, options.scrollStepPx)
      await sleep(scrollIntervalMs)

      const responseCount = this.captureManager.getResponses(captureKey).length
      if (responseCount > lastResponseCount) {
        lastResponseCount = responseCount
        idleRounds = 0
      } else {
        idleRounds += 1
      }

      if (!moved && idleRounds >= maxIdleRounds) {
        break
      }
      if (idleRounds >= maxIdleRounds) {
        break
      }
    }

    let settleRounds = 0
    while (settleRounds < 2) {
      await sleep(settleWaitMs)
      const responseCount = this.captureManager.getResponses(captureKey).length
      if (responseCount > lastResponseCount) {
        lastResponseCount = responseCount
        settleRounds = 0
        continue
      }
      settleRounds += 1
    }

    const responses = await this.captureManager.disposeJsonResponseCaptureSession(this.page, captureKey)
    return responses.map((item) => item.body)
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
    const timeoutMs = Math.max(0, Number(options?.timeoutMs ?? 5000))
    const intervalMs = Math.max(50, Number(options?.intervalMs ?? 250))
    const deadline = Date.now() + timeoutMs
    const pick = options?.pick ?? 'first'
    const trim = options?.trim ?? true
    const preserveLineBreaks = options?.preserveLineBreaks ?? false
    const visibleOnly = options?.visibleOnly ?? false

    while (Date.now() < deadline) {
      const locator = this.page.locator(selector)
      const count = await locator.count().catch(() => 0)
      if (count > 0) {
        const values: string[] = []
        for (let index = 0; index < count; index += 1) {
          const current = locator.nth(index)
          if (visibleOnly) {
            const visible = await current.isVisible().catch(() => false)
            if (!visible) continue
          }
          const rawValue = preserveLineBreaks
            ? await current.innerText().catch(async () => String((await current.textContent().catch(() => '')) || ''))
            : await current.textContent().catch(() => '')
          const normalized = trim ? String(rawValue || '').trim() : String(rawValue || '')
          if (normalized) {
            values.push(normalized)
          }
        }

        if (values.length > 0) {
          return pick === 'last' ? values[values.length - 1] : values[0]
        }
      }

      await sleep(intervalMs)
    }

    return ''
  }

  private async resolveBestLocator(selector: string): Promise<Locator> {
    const locator = this.page.locator(selector)
    const count = await locator.count()
    if (count === 0) {
      throw new Error(`未找到选择器: ${selector}`)
    }

    let fallback: Locator | null = null
    for (let index = 0; index < count; index += 1) {
      const current = locator.nth(index)
      fallback = fallback ?? current
      const visible = await current.isVisible().catch(() => false)
      if (visible) {
        return current
      }
    }

    return fallback!
  }

  private async scrollContainerOnce(scrollContainerSelector?: string, stepPx?: number): Promise<boolean> {
    const scrollStepPx = Number(stepPx ?? 1200)
    if (scrollContainerSelector) {
      const container = this.page.locator(scrollContainerSelector).first()
      const count = await container.count().catch(() => 0)
      if (!count) {
        return false
      }

      return await container.evaluate((node, step) => {
        const target = node as HTMLElement
        const before = target.scrollTop
        const maxScrollTop = Math.max(0, target.scrollHeight - target.clientHeight)
        const nextTop = Math.min(before + Number(step || 0), maxScrollTop)
        target.scrollTop = nextTop
        return nextTop !== before
      }, scrollStepPx)
    }

    return await this.page.evaluate((step) => {
      const target = document.scrollingElement || document.documentElement || document.body
      const before = target.scrollTop
      const maxScrollTop = Math.max(0, target.scrollHeight - window.innerHeight)
      const nextTop = Math.min(before + Number(step || 0), maxScrollTop)
      target.scrollTop = nextTop
      return nextTop !== before
    }, scrollStepPx)
  }
}
