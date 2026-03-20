import { mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import * as XLSX from 'xlsx'
import {
  BrowserAction,
  BrowserApiCollectionField,
  BrowserTask,
  BrowserSelectorState
} from './browser-actions'
import { TaskDSLRunner } from './runner'
import { TaskLoggerLike } from './types'

export interface BrowserActionTarget {
  openView(url: string | null): Promise<void>
  waitForDelay(ms: number): Promise<void>
  waitForBodyText(text: string, timeoutMs?: number, intervalMs?: number): Promise<boolean>
  waitForSelector(
    selector: string,
    options?: { state?: BrowserSelectorState; timeoutMs?: number; intervalMs?: number }
  ): Promise<boolean>
  clickSelector(selector: string, options?: { native?: boolean }): Promise<void>
  clickByText(
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
  ): Promise<void>
  fillSelector(
    selector: string,
    value: string,
    options?: { clearBeforeFill?: boolean; timeoutMs?: number; intervalMs?: number }
  ): Promise<void>
  setCheckbox(
    selector: string,
    options?: {
      checked?: boolean
      timeoutMs?: number
      intervalMs?: number
      scrollContainerSelector?: string
      scrollStepPx?: number
      maxScrollAttempts?: number
    }
  ): Promise<void>
  pressKey(key: string, options?: { native?: boolean }): Promise<void>
  getCurrentUrl(): Promise<string>
  startJsonResponseCapture(options: { captureKey: string; urlIncludes: string; method?: string; reset?: boolean }): Promise<void>
  collectJsonResponsesByScrolling(options: {
    captureKey: string
    initialWaitMs?: number
    scrollContainerSelector?: string
    scrollStepPx?: number
    scrollIntervalMs?: number
    settleWaitMs?: number
    maxIdleRounds?: number
    maxScrollRounds?: number
  }): Promise<unknown[]>
  readText(
    selector: string,
    options?: {
      timeoutMs?: number
      intervalMs?: number
      trim?: boolean
      preserveLineBreaks?: boolean
      pick?: 'first' | 'last'
      visibleOnly?: boolean
    }
  ): Promise<string>
}

export class BrowserActionRunner {
  private readonly runner: TaskDSLRunner<BrowserAction>

  constructor(
    private readonly logger: TaskLoggerLike,
    private readonly target: BrowserActionTarget
  ) {
    this.runner = new TaskDSLRunner<BrowserAction>(logger)
  }

  private async waitForSelectorOrThrow(
    selector: string,
    options?: { state?: BrowserSelectorState; timeoutMs?: number; intervalMs?: number; errorPrefix?: string }
  ): Promise<void> {
    const state = options?.state ?? 'present'
    const timeoutMs = Number(options?.timeoutMs ?? 10000)
    const intervalMs = Number(options?.intervalMs ?? 250)
    const ok = await this.target.waitForSelector(selector, { state, timeoutMs, intervalMs })
    if (!ok) {
      throw new Error(`${options?.errorPrefix ?? '未满足选择器状态'}: selector=${selector}, state=${String(state)}`)
    }
  }

  private async clickTextStep(
    text: string | string[],
    options: {
      selector: string
      exact?: boolean
      caseSensitive?: boolean
      timeoutMs?: number
      intervalMs?: number
      scrollContainerSelector?: string
      scrollStepPx?: number
      maxScrollAttempts?: number
      postClickWaitMs?: number
    }
  ): Promise<void> {
    const texts = Array.isArray(text) ? text : [text]
    const errors: string[] = []
    let clicked = false

    for (const candidate of texts) {
      try {
        await this.target.clickByText(candidate, {
          selector: options.selector,
          exact: options.exact,
          caseSensitive: options.caseSensitive,
          timeoutMs: options.timeoutMs,
          intervalMs: options.intervalMs,
          scrollContainerSelector: options.scrollContainerSelector,
          scrollStepPx: options.scrollStepPx,
          maxScrollAttempts: options.maxScrollAttempts
        })
        clicked = true
        break
      } catch (error) {
        errors.push((error as Error)?.message || String(error))
      }
    }

    if (!clicked) {
      throw new Error(errors.join(' | '))
    }

    const postClickWaitMs = Math.max(0, Number(options.postClickWaitMs ?? 0))
    if (postClickWaitMs > 0) {
      await this.target.waitForDelay(postClickWaitMs)
    }
  }

  private async closeDropdownTrigger(options: {
    closeAfterAction?: boolean
    triggerText: string
    triggerFallbackTexts?: string[]
    triggerSelector: string
    triggerExact?: boolean
    closeText?: string
    closeSelector?: string
    closeFallbackTexts?: string[]
    closeExact?: boolean
    timeoutMs?: number
    intervalMs?: number
    triggerPostClickWaitMs?: number
    closeWaitSelector?: string
    closeWaitState?: BrowserSelectorState
  }): Promise<void> {
    if (options.closeAfterAction === false) {
      return
    }

    const closeText = String(options.closeText || options.triggerText).trim()
    const closeSelector = String(options.closeSelector || options.triggerSelector).trim()
    const closeFallbackTexts =
      options.closeFallbackTexts ?? (options.closeText ? [] : (options.triggerFallbackTexts ?? []))
    const closeExact = options.closeExact ?? options.triggerExact ?? true

    await this.clickTextStep([closeText, ...closeFallbackTexts], {
      selector: closeSelector,
      exact: closeExact,
      caseSensitive: false,
      timeoutMs: options.timeoutMs,
      intervalMs: options.intervalMs,
      postClickWaitMs: options.triggerPostClickWaitMs ?? 250
    })

    if (options.closeWaitSelector) {
      await this.waitForSelectorOrThrow(options.closeWaitSelector, {
        state: options.closeWaitState ?? 'hidden',
        timeoutMs: options.timeoutMs,
        intervalMs: options.intervalMs,
        errorPrefix: '关闭面板后状态不符合预期'
      })
    }
  }

  private readValueAtPath(source: unknown, path: string): unknown {
    if (!path) return source
    return path.split('.').reduce<unknown>((current, segment) => {
      if (current === null || current === undefined) return undefined
      if (Array.isArray(current) && /^\d+$/.test(segment)) {
        return current[Number(segment)]
      }
      if (typeof current === 'object') {
        return (current as Record<string, unknown>)[segment]
      }
      return undefined
    }, source)
  }

  private normalizeCollectedFieldValue(field: BrowserApiCollectionField, item: unknown): unknown {
    const rawValue = this.readValueAtPath(item, field.path)
    if (Array.isArray(rawValue)) {
      const nextValues =
        field.arrayItemPath && field.arrayItemPath.trim()
          ? rawValue
              .map((entry) => this.readValueAtPath(entry, field.arrayItemPath!))
              .filter((entry) => entry !== null && entry !== undefined && String(entry).trim() !== '')
          : rawValue
      const joined = nextValues.map((entry) => String(entry)).join(field.joinWith ?? ',')
      return joined || (field.defaultValue ?? '')
    }
    if (rawValue === null || rawValue === undefined || String(rawValue).trim() === '') {
      return field.defaultValue ?? ''
    }
    return rawValue
  }

  private buildTimestamp(): string {
    const now = new Date()
    const year = now.getFullYear()
    const month = String(now.getMonth() + 1).padStart(2, '0')
    const day = String(now.getDate()).padStart(2, '0')
    const hour = String(now.getHours()).padStart(2, '0')
    const minute = String(now.getMinutes()).padStart(2, '0')
    const second = String(now.getSeconds()).padStart(2, '0')
    const millisecond = String(now.getMilliseconds()).padStart(3, '0')
    return `${year}${month}${day}_${hour}${minute}${second}${millisecond}`
  }

  private persistCollectedItems(
    items: unknown[],
    options?: { outputDir?: string; outputFilePrefix?: string }
  ): string {
    const outputDir = join(process.cwd(), options?.outputDir || 'data/outreach')
    mkdirSync(outputDir, { recursive: true })

    const filePrefix = String(options?.outputFilePrefix || 'creator_marketplace')
      .trim()
      .replace(/[^a-zA-Z0-9_-]+/g, '_')
    const filePath = join(outputDir, `${filePrefix}_${this.buildTimestamp()}.json`)

    writeFileSync(
      filePath,
      JSON.stringify(
        {
          generated_at: new Date().toISOString(),
          total: items.length,
      items
        },
        null,
        2
      )
    )
    return filePath
  }

  private persistCollectedItemsAsDirectory(
    items: unknown[],
    options?: { outputDir?: string; outputDirPrefix?: string; itemKeyPath?: string }
  ): string {
    const parentDir = join(process.cwd(), options?.outputDir || 'data/outreach')
    mkdirSync(parentDir, { recursive: true })

    const dirPrefix = String(options?.outputDirPrefix || 'creator_marketplace_raw_items')
      .trim()
      .replace(/[^a-zA-Z0-9_-]+/g, '_')
    const outputDir = join(parentDir, `${dirPrefix}_${this.buildTimestamp()}`)
    mkdirSync(outputDir, { recursive: true })

    const itemKeyPath = String(options?.itemKeyPath || '').trim()
    items.forEach((item, index) => {
      const rawKey = itemKeyPath ? this.readValueAtPath(item, itemKeyPath) : undefined
      const fileKey = String(rawKey ?? `item_${String(index + 1).padStart(4, '0')}`)
        .trim()
        .replace(/[^a-zA-Z0-9_-]+/g, '_')
      const filePath = join(outputDir, `${fileKey || `item_${String(index + 1).padStart(4, '0')}`}.json`)
      writeFileSync(
        filePath,
        JSON.stringify(
          {
            generated_at: new Date().toISOString(),
            item
          },
          null,
          2
        )
      )
    })

    return outputDir
  }

  private persistCollectedItemsAsExcel(
    items: Array<Record<string, unknown>>,
    columns: string[],
    options?: {
      outputDir?: string
      outputFilePrefix?: string
      responseBatches?: Array<{ sheetName: string; rows: Array<Record<string, unknown>> }>
    }
  ): string {
    const outputDir = join(process.cwd(), options?.outputDir || 'data/outreach')
    mkdirSync(outputDir, { recursive: true })

    const filePrefix = String(options?.outputFilePrefix || 'creator_marketplace')
      .trim()
      .replace(/[^a-zA-Z0-9_-]+/g, '_')
    const filePath = join(outputDir, `${filePrefix}_${this.buildTimestamp()}.xlsx`)

    const workbook = XLSX.utils.book_new()
    this.appendCollectedItemsSheet(workbook, 'all_creators', items, columns)

    const responseBatches = Array.isArray(options?.responseBatches) ? options.responseBatches : []
    responseBatches.forEach((batch) => {
      this.appendCollectedItemsSheet(workbook, batch.sheetName, batch.rows, columns)
    })

    this.writeWorkbook(filePath, workbook)
    return filePath
  }

  private appendCollectedItemsSheet(
    workbook: XLSX.WorkBook,
    sheetName: string,
    rows: Array<Record<string, unknown>>,
    columns: string[]
  ): void {
    const orderedRows = rows.map((row) => {
      const current: Record<string, string | number | boolean | null> = {}
      columns.forEach((column) => {
        current[column] = this.normalizeExcelCellValue(row[column])
      })
      return current
    })

    const worksheet = XLSX.utils.json_to_sheet(orderedRows, {
      header: columns
    })
    XLSX.utils.book_append_sheet(workbook, worksheet, this.sanitizeExcelSheetName(sheetName))
  }

  private normalizeExcelCellValue(value: unknown): string | number | boolean | null {
    if (value === null || value === undefined) {
      return null
    }
    if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
      return value
    }
    return JSON.stringify(value)
  }

  private sanitizeExcelSheetName(name: string): string {
    const sanitized = String(name || 'sheet')
      .replace(/[\\/?*\[\]:]/g, '_')
      .trim()
    return (sanitized || 'sheet').slice(0, 31)
  }

  private writeWorkbook(filePath: string, workbook: XLSX.WorkBook): void {
    const buffer = XLSX.write(workbook, {
      type: 'buffer',
      bookType: 'xlsx'
    })
    writeFileSync(filePath, buffer)
  }

  public async execute(task: BrowserTask): Promise<Record<string, unknown>> {
    return this.runner.execute(task, {
      goto: async (action) => {
        await this.target.openView(action.payload.url)
        const postLoadWaitMs = Math.max(0, Number(action.payload.postLoadWaitMs ?? 0))
        if (postLoadWaitMs > 0) {
          await this.target.waitForDelay(postLoadWaitMs)
        }
      },
      waitForBodyText: async (action) => {
        const found = await this.target.waitForBodyText(
          action.payload.text,
          Number(action.payload.timeoutMs),
          Number(action.payload.intervalMs ?? 500)
        )
        if (found) {
          return
        }

        const recoveryGotoUrl = String(action.recovery?.gotoUrl || '')
        if (recoveryGotoUrl) {
          this.logger.warn(`未检测到文案 "${action.payload.text}"，执行重跳: ${recoveryGotoUrl}`)
          await this.target.openView(recoveryGotoUrl)
          const retryWait = Math.max(0, Number(action.recovery?.postLoadWaitMs ?? 0))
          if (retryWait > 0) {
            await this.target.waitForDelay(retryWait)
          }
        }

        throw new Error(`页面未检测到目标文案: ${action.payload.text}`)
      },
      waitForSelector: async (action) => {
        const ok = await this.target.waitForSelector(action.payload.selector, {
          state: action.payload.state ?? 'present',
          timeoutMs: Number(action.payload.timeoutMs),
          intervalMs: Number(action.payload.intervalMs ?? 250)
        })
        if (ok) {
          return
        }

        const recoveryGotoUrl = String(action.recovery?.gotoUrl || '')
        if (recoveryGotoUrl) {
          this.logger.warn(`未满足选择器状态，执行重跳: ${recoveryGotoUrl}`)
          await this.target.openView(recoveryGotoUrl)
          const retryWait = Math.max(0, Number(action.recovery?.postLoadWaitMs ?? 0))
          if (retryWait > 0) {
            await this.target.waitForDelay(retryWait)
          }
        }

        throw new Error(
          `未满足选择器状态: selector=${action.payload.selector}, state=${String(action.payload.state ?? 'present')}`
        )
      },
      clickSelector: async (action) => {
        const waitForState = action.payload.waitForState
        if (waitForState) {
          const selectorReady = await this.target.waitForSelector(action.payload.selector, {
            state: waitForState,
            timeoutMs: Number(action.payload.timeoutMs ?? 10000),
            intervalMs: Number(action.payload.intervalMs ?? 250)
          })
          if (!selectorReady) {
            throw new Error(
              `点击前等待选择器失败: selector=${action.payload.selector}, state=${String(waitForState)}`
            )
          }
        }

        await this.target.clickSelector(action.payload.selector, {
          native: action.payload.native
        })
        const postClickWaitMs = Math.max(0, Number(action.payload.postClickWaitMs ?? 0))
        if (postClickWaitMs > 0) {
          await this.target.waitForDelay(postClickWaitMs)
        }
      },
      clickByText: async (action) => {
        await this.clickTextStep([action.payload.text, ...(action.payload.fallbackTexts ?? [])], {
          selector: action.payload.selector,
          exact: action.payload.exact,
          caseSensitive: action.payload.caseSensitive,
          timeoutMs: action.payload.timeoutMs,
          intervalMs: action.payload.intervalMs,
          scrollContainerSelector: action.payload.scrollContainerSelector,
          scrollStepPx: action.payload.scrollStepPx,
          maxScrollAttempts: action.payload.maxScrollAttempts,
          postClickWaitMs: action.payload.postClickWaitMs
        })
      },
      fillSelector: async (action) => {
        const waitForState = action.payload.waitForState
        if (waitForState) {
          const selectorReady = await this.target.waitForSelector(action.payload.selector, {
            state: waitForState,
            timeoutMs: Number(action.payload.timeoutMs ?? 10000),
            intervalMs: Number(action.payload.intervalMs ?? 250)
          })
          if (!selectorReady) {
            throw new Error(
              `填值前等待选择器失败: selector=${action.payload.selector}, state=${String(waitForState)}`
            )
          }
        }

        await this.target.fillSelector(action.payload.selector, action.payload.value, {
          clearBeforeFill: action.payload.clearBeforeFill,
          timeoutMs: action.payload.timeoutMs,
          intervalMs: action.payload.intervalMs
        })

        const postFillWaitMs = Math.max(0, Number(action.payload.postFillWaitMs ?? 0))
        if (postFillWaitMs > 0) {
          await this.target.waitForDelay(postFillWaitMs)
        }
      },
      setCheckbox: async (action) => {
        await this.target.setCheckbox(action.payload.selector, {
          checked: action.payload.checked ?? true,
          timeoutMs: action.payload.timeoutMs,
          intervalMs: action.payload.intervalMs,
          scrollContainerSelector: action.payload.scrollContainerSelector,
          scrollStepPx: action.payload.scrollStepPx,
          maxScrollAttempts: action.payload.maxScrollAttempts
        })

        const postClickWaitMs = Math.max(0, Number(action.payload.postClickWaitMs ?? 0))
        if (postClickWaitMs > 0) {
          await this.target.waitForDelay(postClickWaitMs)
        }
      },
      selectDropdownSingle: async (action) => {
        const waitSelector = action.payload.waitSelector ?? action.payload.optionSelector
        const waitState = action.payload.waitState ?? 'visible'

        await this.clickTextStep([action.payload.triggerText, ...(action.payload.triggerFallbackTexts ?? [])], {
          selector: action.payload.triggerSelector,
          exact: action.payload.triggerExact ?? true,
          caseSensitive: false,
          timeoutMs: action.payload.timeoutMs,
          intervalMs: action.payload.intervalMs,
          postClickWaitMs: action.payload.triggerPostClickWaitMs ?? 300
        })
        await this.waitForSelectorOrThrow(waitSelector, {
          state: waitState,
          timeoutMs: action.payload.timeoutMs,
          intervalMs: action.payload.intervalMs,
          errorPrefix: '打开单选下拉失败'
        })
        await this.clickTextStep(action.payload.optionText, {
          selector: action.payload.optionSelector,
          exact: action.payload.exact,
          caseSensitive: action.payload.caseSensitive,
          timeoutMs: action.payload.timeoutMs,
          intervalMs: action.payload.intervalMs,
          scrollContainerSelector: action.payload.scrollContainerSelector,
          scrollStepPx: action.payload.scrollStepPx,
          maxScrollAttempts: action.payload.maxScrollAttempts,
          postClickWaitMs: action.payload.optionPostClickWaitMs ?? 160
        })
        await this.closeDropdownTrigger({
          closeAfterAction: action.payload.closeAfterSelect,
          triggerText: action.payload.triggerText,
          triggerFallbackTexts: action.payload.triggerFallbackTexts,
          triggerSelector: action.payload.triggerSelector,
          triggerExact: action.payload.triggerExact,
          closeText: action.payload.closeText,
          closeSelector: action.payload.closeSelector,
          timeoutMs: action.payload.timeoutMs,
          intervalMs: action.payload.intervalMs,
          triggerPostClickWaitMs: action.payload.triggerPostClickWaitMs ?? 250,
          closeWaitSelector: action.payload.closeWaitSelector,
          closeWaitState: action.payload.closeWaitState
        })
      },
      selectDropdownMultiple: async (action) => {
        const waitSelector = action.payload.waitSelector ?? action.payload.optionSelector
        const waitState = action.payload.waitState ?? 'visible'

        await this.clickTextStep([action.payload.triggerText, ...(action.payload.triggerFallbackTexts ?? [])], {
          selector: action.payload.triggerSelector,
          exact: action.payload.triggerExact ?? true,
          caseSensitive: false,
          timeoutMs: action.payload.timeoutMs,
          intervalMs: action.payload.intervalMs,
          postClickWaitMs: action.payload.triggerPostClickWaitMs ?? 300
        })
        await this.waitForSelectorOrThrow(waitSelector, {
          state: waitState,
          timeoutMs: action.payload.timeoutMs,
          intervalMs: action.payload.intervalMs,
          errorPrefix: '打开多选下拉失败'
        })

        for (const optionText of action.payload.optionTexts) {
          try {
            await this.clickTextStep(optionText, {
              selector: action.payload.optionSelector,
              exact: action.payload.exact,
              caseSensitive: action.payload.caseSensitive,
              timeoutMs: action.payload.timeoutMs,
              intervalMs: action.payload.intervalMs,
              scrollContainerSelector: action.payload.scrollContainerSelector,
              scrollStepPx: action.payload.scrollStepPx,
              maxScrollAttempts: action.payload.maxScrollAttempts,
              postClickWaitMs: action.payload.optionPostClickWaitMs ?? 180
            })
          } catch (error) {
            if (!action.payload.continueOnMissingOptions) {
              throw error
            }
            this.logger.warn(
              `多选项未命中，跳过该选项: text=${optionText}, reason=${(error as Error)?.message || String(error)}`
            )
          }
        }

        await this.closeDropdownTrigger({
          closeAfterAction: action.payload.closeAfterSelect,
          triggerText: action.payload.triggerText,
          triggerFallbackTexts: action.payload.triggerFallbackTexts,
          triggerSelector: action.payload.triggerSelector,
          triggerExact: action.payload.triggerExact,
          closeText: action.payload.closeText,
          closeSelector: action.payload.closeSelector,
          timeoutMs: action.payload.timeoutMs,
          intervalMs: action.payload.intervalMs,
          triggerPostClickWaitMs: action.payload.triggerPostClickWaitMs ?? 250,
          closeWaitSelector: action.payload.closeWaitSelector,
          closeWaitState: action.payload.closeWaitState
        })
      },
      selectCascaderOptionsByValue: async (action) => {
        const inputSelector = action.payload.inputSelector ?? 'input[type="checkbox"]'
        const valueAttribute = action.payload.valueAttribute ?? 'value'

        await this.clickTextStep([action.payload.triggerText, ...(action.payload.triggerFallbackTexts ?? [])], {
          selector: action.payload.triggerSelector,
          exact: action.payload.triggerExact ?? true,
          caseSensitive: false,
          timeoutMs: action.payload.timeoutMs,
          intervalMs: action.payload.intervalMs,
          postClickWaitMs: action.payload.triggerPostClickWaitMs ?? 300
        })
        await this.waitForSelectorOrThrow(action.payload.panelSelector, {
          state: 'visible',
          timeoutMs: action.payload.timeoutMs,
          intervalMs: action.payload.intervalMs,
          errorPrefix: '打开级联面板失败'
        })

        for (const value of action.payload.values) {
          const optionSelector = `${action.payload.panelSelector} ${inputSelector}[${valueAttribute}="${value}"]`
          await this.target.setCheckbox(optionSelector, {
            checked: true,
            timeoutMs: action.payload.timeoutMs,
            intervalMs: action.payload.intervalMs,
            scrollContainerSelector: action.payload.scrollContainerSelector ?? action.payload.panelSelector,
            scrollStepPx: action.payload.scrollStepPx,
            maxScrollAttempts: action.payload.maxScrollAttempts
          })
          const optionPostClickWaitMs = Math.max(0, Number(action.payload.optionPostClickWaitMs ?? 180))
          if (optionPostClickWaitMs > 0) {
            await this.target.waitForDelay(optionPostClickWaitMs)
          }
        }

        await this.closeDropdownTrigger({
          closeAfterAction: action.payload.closeAfterSelect,
          triggerText: action.payload.triggerText,
          triggerFallbackTexts: action.payload.triggerFallbackTexts,
          triggerSelector: action.payload.triggerSelector,
          triggerExact: action.payload.triggerExact,
          closeText: action.payload.closeText,
          closeSelector: action.payload.closeSelector,
          timeoutMs: action.payload.timeoutMs,
          intervalMs: action.payload.intervalMs,
          triggerPostClickWaitMs: action.payload.triggerPostClickWaitMs ?? 250,
          closeWaitSelector: action.payload.closeWaitSelector,
          closeWaitState: action.payload.closeWaitState
        })
      },
      fillDropdownRange: async (action) => {
        await this.clickTextStep([action.payload.triggerText, ...(action.payload.triggerFallbackTexts ?? [])], {
          selector: action.payload.triggerSelector,
          exact: action.payload.triggerExact ?? true,
          caseSensitive: false,
          timeoutMs: action.payload.timeoutMs,
          intervalMs: action.payload.intervalMs,
          postClickWaitMs: action.payload.triggerPostClickWaitMs ?? 300
        })
        await this.waitForSelectorOrThrow(action.payload.waitSelector, {
          state: 'visible',
          timeoutMs: action.payload.timeoutMs,
          intervalMs: action.payload.intervalMs,
          errorPrefix: '打开区间输入面板失败'
        })

        await this.target.fillSelector(action.payload.minSelector, action.payload.minValue, {
          clearBeforeFill: true,
          timeoutMs: action.payload.timeoutMs,
          intervalMs: action.payload.intervalMs
        })
        const fillPostWaitMs = Math.max(0, Number(action.payload.fillPostWaitMs ?? 120))
        if (fillPostWaitMs > 0) {
          await this.target.waitForDelay(fillPostWaitMs)
        }
        await this.target.fillSelector(action.payload.maxSelector, action.payload.maxValue, {
          clearBeforeFill: true,
          timeoutMs: action.payload.timeoutMs,
          intervalMs: action.payload.intervalMs
        })
        if (fillPostWaitMs > 0) {
          await this.target.waitForDelay(fillPostWaitMs)
        }

        await this.closeDropdownTrigger({
          closeAfterAction: action.payload.closeAfterFill,
          triggerText: action.payload.triggerText,
          triggerFallbackTexts: action.payload.triggerFallbackTexts,
          triggerSelector: action.payload.triggerSelector,
          triggerExact: action.payload.triggerExact,
          closeText: action.payload.closeText,
          closeSelector: action.payload.closeSelector,
          timeoutMs: action.payload.timeoutMs,
          intervalMs: action.payload.intervalMs,
          triggerPostClickWaitMs: action.payload.triggerPostClickWaitMs ?? 250,
          closeWaitSelector: action.payload.closeWaitSelector,
          closeWaitState: action.payload.closeWaitState
        })
      },
      fillDropdownThreshold: async (action) => {
        await this.clickTextStep([action.payload.triggerText, ...(action.payload.triggerFallbackTexts ?? [])], {
          selector: action.payload.triggerSelector,
          exact: action.payload.triggerExact ?? true,
          caseSensitive: false,
          timeoutMs: action.payload.timeoutMs,
          intervalMs: action.payload.intervalMs,
          postClickWaitMs: action.payload.triggerPostClickWaitMs ?? 300
        })
        await this.waitForSelectorOrThrow(action.payload.waitSelector, {
          state: 'visible',
          timeoutMs: action.payload.timeoutMs,
          intervalMs: action.payload.intervalMs,
          errorPrefix: '打开阈值输入面板失败'
        })

        await this.target.fillSelector(action.payload.inputSelector, action.payload.value, {
          clearBeforeFill: true,
          timeoutMs: action.payload.timeoutMs,
          intervalMs: action.payload.intervalMs
        })
        const fillPostWaitMs = Math.max(0, Number(action.payload.fillPostWaitMs ?? 120))
        if (fillPostWaitMs > 0) {
          await this.target.waitForDelay(fillPostWaitMs)
        }

        if (action.payload.checkboxLabelText && action.payload.checkboxLabelSelector) {
          await this.clickTextStep(action.payload.checkboxLabelText, {
            selector: action.payload.checkboxLabelSelector,
            exact: action.payload.checkboxExact ?? false,
            caseSensitive: false,
            timeoutMs: action.payload.timeoutMs,
            intervalMs: action.payload.intervalMs,
            postClickWaitMs: action.payload.checkboxPostClickWaitMs ?? 150
          })
        }

        await this.closeDropdownTrigger({
          closeAfterAction: action.payload.closeAfterFill,
          triggerText: action.payload.triggerText,
          triggerFallbackTexts: action.payload.triggerFallbackTexts,
          triggerSelector: action.payload.triggerSelector,
          triggerExact: action.payload.triggerExact,
          closeText: action.payload.closeText,
          closeSelector: action.payload.closeSelector,
          timeoutMs: action.payload.timeoutMs,
          intervalMs: action.payload.intervalMs,
          triggerPostClickWaitMs: action.payload.triggerPostClickWaitMs ?? 250,
          closeWaitSelector: action.payload.closeWaitSelector,
          closeWaitState: action.payload.closeWaitState
        })
      },
      pressKey: async (action) => {
        await this.target.pressKey(action.payload.key, {
          native: action.payload.native
        })
        const postKeyWaitMs = Math.max(0, Number(action.payload.postKeyWaitMs ?? 0))
        if (postKeyWaitMs > 0) {
          await this.target.waitForDelay(postKeyWaitMs)
        }
      },
      assertUrlContains: async (action) => {
        const currentUrl = await this.target.getCurrentUrl()
        if (!currentUrl.includes(action.payload.keyword)) {
          throw new Error(`当前 URL 不包含关键字: keyword=${action.payload.keyword}, url=${currentUrl}`)
        }
      },
      startJsonResponseCapture: async (action) => {
        await this.target.startJsonResponseCapture({
          captureKey: action.payload.captureKey,
          urlIncludes: action.payload.urlIncludes,
          method: action.payload.method,
          reset: action.payload.reset ?? true
        })
      },
      collectApiItemsByScrolling: async (action, context) => {
        const responses = await this.target.collectJsonResponsesByScrolling({
          captureKey: action.payload.captureKey,
          initialWaitMs: action.payload.initialWaitMs,
          scrollContainerSelector: action.payload.scrollContainerSelector,
          scrollStepPx: action.payload.scrollStepPx,
          scrollIntervalMs: action.payload.scrollIntervalMs,
          settleWaitMs: action.payload.settleWaitMs,
          maxIdleRounds: action.payload.maxIdleRounds,
          maxScrollRounds: action.payload.maxScrollRounds
        })

        const dedupeByPath = String(action.payload.dedupeByPath || '').trim()
        const listPath = action.payload.responseListPath
        const columns = action.payload.fields.map((field) => field.key)
        const seen = new Set<string>()
        const items: Array<Record<string, unknown>> = []
        const rawItems: unknown[] = []
        const responseBatches: Array<{ sheetName: string; rows: Array<Record<string, unknown>> }> = []

        for (const [responseIndex, response] of responses.entries()) {
          const list = this.readValueAtPath(response, listPath)
          if (!Array.isArray(list)) continue

          const batchRows: Array<Record<string, unknown>> = []

          for (const entry of list) {
            const mapped: Record<string, unknown> = {}
            for (const field of action.payload.fields) {
              mapped[field.key] = this.normalizeCollectedFieldValue(field, entry)
            }
            batchRows.push(mapped)

            const dedupeValue = dedupeByPath ? this.readValueAtPath(entry, dedupeByPath) : undefined
            const dedupeKey = dedupeValue === undefined ? '' : String(dedupeValue)
            if (dedupeKey && seen.has(dedupeKey)) continue
            if (dedupeKey) {
              seen.add(dedupeKey)
            }

            rawItems.push(entry)
            items.push(mapped)
          }

          if (batchRows.length > 0) {
            responseBatches.push({
              sheetName: `request_${String(responseIndex + 1).padStart(3, '0')}`,
              rows: batchRows
            })
          }
        }

        context.data[action.payload.saveAs] = items

        const summary = {
          capture_key: action.payload.captureKey,
          response_count: responses.length,
          collected_count: items.length
        }
        if (action.payload.saveSummaryAs) {
          context.data[action.payload.saveSummaryAs] = summary
        }

        if (action.payload.saveFilePathAs) {
          const filePath = this.persistCollectedItems(items, {
            outputDir: action.payload.outputDir,
            outputFilePrefix: action.payload.outputFilePrefix
          })
          context.data[action.payload.saveFilePathAs] = filePath
        }

        if (action.payload.saveExcelFilePathAs) {
          const excelFilePath = this.persistCollectedItemsAsExcel(items, columns, {
            outputDir: action.payload.excelOutputDir ?? action.payload.outputDir,
            outputFilePrefix: action.payload.excelOutputFilePrefix ?? action.payload.outputFilePrefix,
            responseBatches
          })
          context.data[action.payload.saveExcelFilePathAs] = excelFilePath
        }

        if (action.payload.saveRawItemsAs) {
          context.data[action.payload.saveRawItemsAs] = rawItems
        }

        if (action.payload.saveRawFilePathAs) {
          const rawFilePath = this.persistCollectedItems(rawItems, {
            outputDir: action.payload.rawOutputDir ?? action.payload.outputDir,
            outputFilePrefix: action.payload.rawOutputFilePrefix ?? `${action.payload.outputFilePrefix || 'creator_marketplace'}_raw`
          })
          context.data[action.payload.saveRawFilePathAs] = rawFilePath
        }

        if (action.payload.saveRawDirectoryPathAs) {
          const rawDirectoryPath = this.persistCollectedItemsAsDirectory(rawItems, {
            outputDir: action.payload.rawDirectoryOutputDir ?? action.payload.rawOutputDir ?? action.payload.outputDir,
            outputDirPrefix:
              action.payload.rawDirectoryOutputPrefix ??
              `${action.payload.rawOutputFilePrefix ?? `${action.payload.outputFilePrefix || 'creator_marketplace'}_raw`}_items`,
            itemKeyPath: dedupeByPath
          })
          context.data[action.payload.saveRawDirectoryPathAs] = rawDirectoryPath
        }
      },
      readText: async (action, context) => {
        const value = await this.target.readText(action.payload.selector, {
          timeoutMs: action.payload.timeoutMs,
          intervalMs: action.payload.intervalMs,
          trim: action.payload.trim,
          preserveLineBreaks: action.payload.preserveLineBreaks,
          pick: action.payload.pick,
          visibleOnly: action.payload.visibleOnly
        })
        context.data[action.payload.saveAs] = value
      },
      assertData: async (action, context) => {
        const key = action.payload.key
        const actual = context.data[key]

        if (action.payload.equals !== undefined && actual !== action.payload.equals) {
          throw new Error(`断言失败: data.${key} !== expected (${String(actual)} !== ${String(action.payload.equals)})`)
        }
        if (action.payload.notEquals !== undefined && actual === action.payload.notEquals) {
          throw new Error(`断言失败: data.${key} === forbidden (${String(actual)})`)
        }
        if (action.payload.contains !== undefined) {
          const textValue = String(actual ?? '')
          if (!textValue.includes(action.payload.contains)) {
            throw new Error(`断言失败: data.${key} 不包含 "${action.payload.contains}"，实际 "${textValue}"`)
          }
        }
      },
      waitForTextChange: async (action, context) => {
        const timeoutMs = Math.max(1000, Number(action.payload.timeoutMs))
        const intervalMs = Math.max(50, Number(action.payload.intervalMs ?? 250))
        const startedAt = Date.now()

        let baseline = ''
        if (action.payload.previousKey) {
          baseline = String(context.data[action.payload.previousKey] ?? '')
        } else {
          baseline = await this.target.readText(action.payload.selector, { timeoutMs: 1000, intervalMs, trim: true })
        }

        while (Date.now() - startedAt < timeoutMs) {
          const current = await this.target.readText(action.payload.selector, { timeoutMs: 1000, intervalMs, trim: true })
          if (current !== baseline) {
            const saveKey = action.payload.saveAs || action.payload.previousKey
            if (saveKey) {
              context.data[saveKey] = current
            }
            return
          }
          await this.target.waitForDelay(intervalMs)
        }

        throw new Error(`等待文本变化超时: selector=${action.payload.selector}, baseline="${baseline}"`)
      }
    })
  }
}
