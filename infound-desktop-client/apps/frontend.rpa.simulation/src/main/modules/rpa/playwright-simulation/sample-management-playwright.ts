import { existsSync, mkdirSync, readFileSync, writeFileSync } from 'node:fs'
import { dirname, join } from 'node:path'
import type { Page } from 'playwright'
import * as XLSX from 'xlsx'
import { logger } from '../../../utils/logger'
import { PlaywrightJsonResponseCaptureManager, type CapturedJsonResponse } from './playwright-response-capture'
import { evaluatePageScript, sleep } from './shared'
import {
  SAMPLE_DRAWER_CLOSE_SELECTOR,
  SAMPLE_DRAWER_SELECTOR,
  SAMPLE_GROUP_LIST_URL,
  SAMPLE_MANAGEMENT_SHEET_COLUMNS,
  SAMPLE_MANAGEMENT_TAB_KEYS,
  SAMPLE_NEXT_SELECTOR,
  SAMPLE_PERFORMANCE_URL,
  SAMPLE_TABLE_SELECTOR,
  TAB_CONFIG
} from '../sample-management/config'
import { extractPerformanceSummaryItems, parseSamplePayload, type ParsedSampleManagementPage } from '../sample-management/parser'
import type {
  SampleManagementExportResult,
  SampleManagementRow,
  SampleManagementTabCrawlResult,
  SampleManagementTabKey
} from '../sample-management/types'

export class PlaywrightSampleManagementCrawler {
  private readonly captureManager = new PlaywrightJsonResponseCaptureManager(logger)

  public async crawlTabsAndExportExcel(
    page: Page,
    options?: { tabs?: SampleManagementTabKey[] }
  ): Promise<SampleManagementExportResult> {
    const requestedTabs = options?.tabs?.length ? options.tabs : SAMPLE_MANAGEMENT_TAB_KEYS
    const results = new Map<SampleManagementTabKey, SampleManagementTabCrawlResult>()
    const excelPath = this.initializeWorkbook()
    let firstTab = true

    for (const tab of requestedTabs) {
      logger.info(`开始抓取样品管理 tab(Playwright): ${TAB_CONFIG[tab].displayName}`)
      const result = await this.crawlTabViaApi(page, tab, {
        refreshBeforeCapture: firstTab && tab === 'to_review',
        excelPath
      })
      results.set(tab, result)
      logger.info(
        `样品管理 tab 抓取完成(Playwright): tab=${TAB_CONFIG[tab].displayName} rows=${result.rows.length} pages=${result.pages_visited} responses=${result.responses_captured} stop_reason=${result.stop_reason}`
      )
      firstTab = false
    }

    const toReview = results.get('to_review') || this.emptyTabResult('to_review', 'tab_not_selected_by_task')
    const readyToShip = results.get('ready_to_ship') || this.emptyTabResult('ready_to_ship', 'tab_not_selected_by_task')
    const shipped = results.get('shipped') || this.emptyTabResult('shipped', 'tab_not_selected_by_task')
    const inProgress = results.get('in_progress') || this.emptyTabResult('in_progress', 'tab_not_selected_by_task')
    const completed = results.get('completed') || this.emptyTabResult('completed', 'tab_not_selected_by_task')

    logger.info(`样品管理数据已增量导出 Excel(Playwright): ${excelPath}`)

    return {
      to_review: toReview,
      ready_to_ship: readyToShip,
      shipped,
      in_progress: inProgress,
      completed,
      excel_path: excelPath
    }
  }

  private async crawlTabViaApi(
    page: Page,
    tab: SampleManagementTabKey,
    options: { refreshBeforeCapture: boolean; excelPath: string }
  ): Promise<SampleManagementTabCrawlResult> {
    const captureKey = `sample_management_${tab}_${Date.now()}`
    const knownPageSignatures = new Set<string>()
    const pageSignatures: string[] = []
    const rows: SampleManagementRow[] = []
    const config = TAB_CONFIG[tab]
    let responseCursor = 0
    let pageIndex = 1
    let stopReason = 'completed'
    let responses: CapturedJsonResponse[] = []
    let captureStarted = false

    const startCapture = async (): Promise<void> => {
      if (captureStarted) return
      await this.captureManager.startJsonResponseCapture(page, {
        captureKey,
        urlIncludes: SAMPLE_GROUP_LIST_URL
      })
      captureStarted = true
    }

    try {
      const pageReady = await this.waitForSamplePageReady(page)
      if (!pageReady) {
        stopReason = 'page_not_ready'
        return { tab, rows, pages_visited: 0, responses_captured: 0, stop_reason: stopReason, page_signatures: pageSignatures }
      }

      if (!captureStarted) {
        await startCapture()
      }

      if (options.refreshBeforeCapture) {
        logger.info(`样品管理首屏开始前刷新页面(Playwright): tab=${config.displayName}`)
        await page.reload({ waitUntil: 'domcontentloaded' })
        const reloadedReady = await this.waitForSamplePageReady(page)
        if (!reloadedReady) {
          stopReason = 'page_not_ready_after_reload'
          return { tab, rows, pages_visited: 0, responses_captured: 0, stop_reason: stopReason, page_signatures: pageSignatures }
        }
      } else {
        logger.info(`样品管理准备切换 tab(Playwright): ${config.displayName}`)
        const tabReady = await this.ensureTabSelected(page, config.displayName)
        if (!tabReady) {
          stopReason = `${tab}_tab_not_found`
          return { tab, rows, pages_visited: 0, responses_captured: 0, stop_reason: stopReason, page_signatures: pageSignatures }
        }
      }

      const hardMaxPages = 200
      while (pageIndex <= hardMaxPages) {
        const nextPage = await this.waitForNextSamplePage({
          captureKey,
          responseCursor,
          knownPageSignatures,
          pageIndex,
          tab,
          timeoutMs: pageIndex === 1 ? 30000 : 20000
        })

        if (!nextPage) {
          stopReason = pageIndex === 1 ? 'no_api_response' : 'no_new_unique_response'
          break
        }

        responseCursor = nextPage.nextCursor
        knownPageSignatures.add(nextPage.page.pageSignature)
        pageSignatures.push(nextPage.page.pageSignature)
        logger.info(
          `样品管理已捕获页面响应(Playwright): tab=${config.displayName} page=${pageIndex} rows=${nextPage.page.rows.length}`
        )

        if (tab === 'completed' && nextPage.page.rows.length > 0) {
          await this.enrichCompletedRowsWithContentSummary(page, nextPage.page.rows)
        }

        rows.push(...nextPage.page.rows)
        if (nextPage.page.rows.length > 0) {
          this.appendRowsToWorkbook(options.excelPath, tab, nextPage.page.rows)
          logger.info(
            `样品管理增量保存完成(Playwright): tab=${config.displayName} page=${pageIndex} appended_rows=${nextPage.page.rows.length} total_rows=${rows.length} file=${options.excelPath}`
          )
        }

        if (nextPage.page.hasMore === false) {
          stopReason = 'api_has_more_false'
          break
        }

        logger.info(`样品管理点击分页 Next(Playwright): tab=${config.displayName} current_page=${pageIndex}`)
        const responseCountBeforePaging = this.captureManager.getResponses(captureKey).length
        const moved = await this.clickPaginationNext(page)
        if (!moved) {
          stopReason = 'pagination_next_disabled'
          break
        }
        const hasNewResponseAfterPaging = await this.waitForNewSampleResponseAfterPaging({
          captureKey,
          previousResponseCount: responseCountBeforePaging,
          timeoutMs: 12000
        })
        if (!hasNewResponseAfterPaging) {
          stopReason = 'pagination_no_new_request'
          break
        }

        pageIndex += 1
      }

      if (pageIndex > hardMaxPages) {
        stopReason = 'hard_max_pages_reached'
      }
    } finally {
      responses = await this.captureManager.disposeJsonResponseCaptureSession(page, captureKey)
    }

    return {
      tab,
      rows,
      pages_visited: pageSignatures.length,
      responses_captured: responses.length,
      stop_reason: stopReason,
      page_signatures: pageSignatures
    }
  }

  private async waitForNextSamplePage(options: {
    captureKey: string
    responseCursor: number
    knownPageSignatures: Set<string>
    pageIndex: number
    tab: SampleManagementTabKey
    timeoutMs: number
  }): Promise<{ page: ParsedSampleManagementPage; nextCursor: number } | null> {
    const result = await this.captureManager.waitForNextParsedResponse({
      captureKey: options.captureKey,
      responseCursor: options.responseCursor,
      timeoutMs: options.timeoutMs,
      knownKeys: options.knownPageSignatures,
      parse: (captured) => {
        const parsed = parseSamplePayload(captured.body, options.pageIndex, options.tab)
        if (!parsed) {
          return null
        }
        return {
          key: parsed.pageSignature,
          value: parsed
        }
      }
    })

    if (!result) {
      return null
    }

    return {
      page: result.value,
      nextCursor: result.nextCursor
    }
  }

  private async enrichCompletedRowsWithContentSummary(page: Page, rows: SampleManagementRow[]): Promise<void> {
    for (let rowIndex = 0; rowIndex < rows.length; rowIndex += 1) {
      const row = rows[rowIndex]
      row.content_summary = await this.collectCompletedContentSummaryForRow(page, row, rowIndex)
    }
  }

  private async collectCompletedContentSummaryForRow(
    page: Page,
    row: SampleManagementRow,
    rowIndex: number
  ): Promise<string> {
    const emptySummary = JSON.stringify({ count: 0, items: [] })
    if (!row.sample_request_id) {
      return emptySummary
    }

    const captureKey = `sample_management_completed_content_${row.sample_request_id}_${Date.now()}`
    await this.captureManager.startJsonResponseCapture(page, {
      captureKey,
      urlIncludes: SAMPLE_PERFORMANCE_URL
    })

    let responses: CapturedJsonResponse[] = []
    try {
      const opened = await this.openCompletedViewContentDrawer(page, row, rowIndex)
      if (!opened) {
        logger.warn(`样品管理 Completed 内容抓取失败：未打开侧边页 request=${row.sample_request_id}`)
        return emptySummary
      }
      logger.info(`样品管理 Completed 已打开 View Content(Playwright): request=${row.sample_request_id}`)

      const drawerReady = await this.waitForSelectorState(page, SAMPLE_DRAWER_SELECTOR, 'present', 10000, 200)
      if (!drawerReady) {
        logger.warn(`样品管理 Completed 内容抓取失败：侧边页未出现 request=${row.sample_request_id}`)
        return emptySummary
      }

      await sleep(1200)
      const clickedVideo = await this.clickDrawerTabByText(page, 'Video')
      if (clickedVideo) {
        logger.info(`样品管理 Completed 已点击 Video(Playwright): request=${row.sample_request_id}`)
        await sleep(1200)
      }

      const clickedLive = await this.clickDrawerTabByText(page, 'LIVE')
      if (clickedLive) {
        logger.info(`样品管理 Completed 已点击 LIVE(Playwright): request=${row.sample_request_id}`)
        await sleep(1200)
      }
    } finally {
      responses = await this.captureManager.disposeJsonResponseCaptureSession(page, captureKey)
      await this.closeDrawerIfOpen(page)
    }

    const items = extractPerformanceSummaryItems(responses, row.sample_request_id)
    return JSON.stringify({ count: items.length, items })
  }

  private async waitForSamplePageReady(page: Page): Promise<boolean> {
    const deadline = Date.now() + 30000
    let lastSnapshot: { href: string; matchedLabels: string[]; tabCount: number; hasTable: boolean } | null = null
    while (Date.now() < deadline) {
      lastSnapshot = await evaluatePageScript<{
        href: string
        matchedLabels: string[]
        tabCount: number
        hasTable: boolean
      }>(
        page,
        `(() => {
          const normalize = (value) => String(value ?? '').replace(/\\s+/g, ' ').trim().toLowerCase()
          const href = String(location.href || '')
          const expectedLabels = ['to review', 'ready to ship', 'shipped', 'in progress', 'completed']
          const tabTexts = Array.from(document.querySelectorAll('[role="tab"], .arco-tabs-header-title'))
            .map((node) => normalize(node.textContent))
            .filter(Boolean)
          const bodyText = normalize(document.body?.innerText || '')
          const matchedLabels = expectedLabels.filter(
            (label) => bodyText.includes(label) || tabTexts.some((text) => text.includes(label))
          )
          const hasTable = Boolean(document.querySelector(${JSON.stringify(SAMPLE_TABLE_SELECTOR)}))
          return {
            href,
            matchedLabels,
            tabCount: tabTexts.length,
            hasTable
          }
        })()`
      ).catch(() => null)

      if (
        lastSnapshot?.href.includes('/product/sample-request') &&
        (lastSnapshot.hasTable || lastSnapshot.matchedLabels.length >= 2 || lastSnapshot.tabCount >= 3)
      ) {
        return true
      }
      await sleep(250)
    }
    logger.warn(
      `样品管理页面未就绪(Playwright): url=${lastSnapshot?.href || page.url()} tab_count=${lastSnapshot?.tabCount || 0} matched_tabs=${lastSnapshot?.matchedLabels.join('|') || 'none'} has_table=${lastSnapshot?.hasTable ? 'true' : 'false'}`
    )
    return false
  }

  private async ensureTabSelected(page: Page, label: string, options?: { forceClick?: boolean }): Promise<boolean> {
    return await evaluatePageScript<boolean>(
      page,
      `(() => {
        const targetLabel = ${JSON.stringify(label)}
        const forceClick = ${JSON.stringify(Boolean(options?.forceClick))}
        const normalize = (value) => String(value ?? '').replace(/\\s+/g, ' ').trim().toLowerCase()
        const expected = normalize(targetLabel)
        const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
        const strongClick = (node) => {
          if (!(node instanceof HTMLElement)) return
          node.scrollIntoView({ block: 'center', inline: 'nearest' })
          ;['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach((type) => {
            node.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window }))
          })
        }
        const extractTitle = (node) =>
          normalize(node.querySelector('.m4b-tabs-pane-title-content')?.textContent || node.textContent).replace(/\\s*\\d+\\s*$/, '')
        const isSelected = (node) =>
          node.getAttribute('aria-selected') === 'true' || String(node.getAttribute('class') || '').includes('arco-tabs-header-title-active')

        return (async () => {
          const tabs = Array.from(document.querySelectorAll('[role="tab"], .arco-tabs-header-title'))
          const target = tabs.find((node) => extractTitle(node) === expected)
          if (!target) return false
          if (forceClick || !isSelected(target)) {
            const html = target instanceof HTMLElement ? target : target.querySelector('.m4b-tabs-pane-title-content') || target
            if (html instanceof HTMLElement) {
              strongClick(html)
            } else if (typeof target.click === 'function') {
              target.click()
            } else {
              target.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
            }
            await sleep(1000)
          }
          return isSelected(target) || forceClick
        })()
      })()`
    )
  }

  private async clickPaginationNext(page: Page): Promise<boolean> {
    return await evaluatePageScript<boolean>(
      page,
      `(() => {
        const isVisible = (node) => {
          if (!(node instanceof HTMLElement)) return false
          const style = window.getComputedStyle(node)
          if (style.display === 'none' || style.visibility === 'hidden') return false
          return node.offsetParent !== null || style.position === 'fixed'
        }
        const nextButtons = Array.from(document.querySelectorAll(${JSON.stringify(SAMPLE_NEXT_SELECTOR)})).filter(isVisible)
        const nextButton = nextButtons[nextButtons.length - 1] || null
        if (!nextButton) return false
        const className = String(nextButton.getAttribute('class') || '')
        const disabled =
          nextButton.getAttribute('aria-disabled') === 'true' || className.includes('arco-pagination-item-disabled')
        if (disabled) return false
        if (nextButton instanceof HTMLElement) {
          nextButton.scrollIntoView({ block: 'center', inline: 'nearest' })
          ;['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach((type) => {
            nextButton.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window }))
          })
        } else if (typeof nextButton.click === 'function') nextButton.click()
        return true
      })()`
    )
  }

  private async waitForNewSampleResponseAfterPaging(options: {
    captureKey: string
    previousResponseCount: number
    timeoutMs: number
  }): Promise<boolean> {
    const deadline = Date.now() + options.timeoutMs
    while (Date.now() < deadline) {
      const responseCount = this.captureManager.getResponses(options.captureKey).length
      if (responseCount > options.previousResponseCount) {
        return true
      }
      await sleep(250)
    }
    return false
  }

  private async waitForSelectorState(
    page: Page,
    selector: string,
    state: 'present' | 'visible' | 'absent' | 'hidden',
    timeoutMs: number,
    intervalMs: number
  ): Promise<boolean> {
    const deadline = Date.now() + timeoutMs
    while (Date.now() < deadline) {
      const matched = await evaluatePageScript<boolean>(
        page,
        `(() => {
          const selector = ${JSON.stringify(selector)}
          const state = ${JSON.stringify(state)}
          const isVisible = (element) => {
            if (!(element instanceof HTMLElement)) return false
            const style = window.getComputedStyle(element)
            if (style.display === 'none' || style.visibility === 'hidden') return false
            return element.offsetParent !== null || style.position === 'fixed'
          }
          const nodes = Array.from(document.querySelectorAll(selector))
          if (state === 'present') return nodes.length > 0
          if (state === 'visible') return nodes.some((node) => isVisible(node))
          if (state === 'absent') return nodes.length === 0
          if (state === 'hidden') return nodes.length > 0 && nodes.every((node) => !isVisible(node))
          return false
        })()`
      )
      if (matched) {
        return true
      }
      await sleep(intervalMs)
    }
    return false
  }

  private async openCompletedViewContentDrawer(page: Page, row: SampleManagementRow, rowIndex: number): Promise<boolean> {
    return await evaluatePageScript<boolean>(
      page,
      `(() => {
        const rowIndex = ${JSON.stringify(rowIndex)}
        const creatorName = ${JSON.stringify(row.creator_name)}
        const productName = ${JSON.stringify(row.product_name)}
        const normalize = (value) => String(value ?? '').replace(/\\s+/g, ' ').trim().toLowerCase()
        const isVisible = (node) => {
          if (!(node instanceof HTMLElement)) return false
          const style = window.getComputedStyle(node)
          if (style.display === 'none' || style.visibility === 'hidden') return false
          return node.offsetParent !== null || style.position === 'fixed'
        }

        const rows = Array.from(document.querySelectorAll('tr.arco-table-tr')).filter(isVisible)
        const expectedCreator = normalize(creatorName)
        const expectedCreatorAt = expectedCreator.startsWith('@') ? expectedCreator : '@' + expectedCreator
        const expectedProduct = normalize(productName)

        const targetRow =
          rows.find((rowNode) => {
            const text = normalize(rowNode.textContent)
            const creatorMatched = !expectedCreator || text.includes(expectedCreator) || text.includes(expectedCreatorAt)
            const productMatched = !expectedProduct || text.includes(expectedProduct)
            return creatorMatched && productMatched
          }) || rows[rowIndex] || null

        if (!(targetRow instanceof HTMLElement)) {
          return false
        }

        targetRow.scrollIntoView({ block: 'center', inline: 'nearest' })
        const actionNodes = Array.from(targetRow.querySelectorAll('div[data-e2e="e197794d-b324-d3da"]'))
        const viewContentNode = actionNodes.find((node) => normalize(node.textContent).includes('view content')) || null
        if (!(viewContentNode instanceof HTMLElement)) {
          return false
        }

        viewContentNode.scrollIntoView({ block: 'center', inline: 'nearest' })
        ;['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach((type) => {
          viewContentNode.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window }))
        })
        return true
      })()`
    )
  }

  private async clickDrawerTabByText(page: Page, label: string): Promise<boolean> {
    return await evaluatePageScript<boolean>(
      page,
      `(() => {
        const label = ${JSON.stringify(label)}
        const normalize = (value) => String(value ?? '').replace(/\\s+/g, ' ').trim().toLowerCase()
        const isVisible = (node) => {
          if (!(node instanceof HTMLElement)) return false
          const style = window.getComputedStyle(node)
          if (style.display === 'none' || style.visibility === 'hidden') return false
          return node.offsetParent !== null || style.position === 'fixed'
        }

        const drawers = Array.from(document.querySelectorAll(${JSON.stringify(SAMPLE_DRAWER_SELECTOR)})).filter(isVisible)
        const drawer = drawers[drawers.length - 1]
        if (!(drawer instanceof HTMLElement)) {
          return false
        }

        const tabs = Array.from(drawer.querySelectorAll('[role="tab"], .arco-tabs-header-title'))
        const target = tabs.find((tab) => normalize(tab.textContent).includes(normalize(label)))
        if (!(target instanceof HTMLElement)) {
          return false
        }

        target.scrollIntoView({ block: 'nearest', inline: 'nearest' })
        ;['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach((type) => {
          target.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window }))
        })
        return true
      })()`
    )
  }

  private async closeDrawerIfOpen(page: Page): Promise<void> {
    const closed = await evaluatePageScript<boolean>(
      page,
      `(() => {
        const isVisible = (node) => {
          if (!(node instanceof HTMLElement)) return false
          const style = window.getComputedStyle(node)
          if (style.display === 'none' || style.visibility === 'hidden') return false
          return node.offsetParent !== null || style.position === 'fixed'
        }
        const closeNode = Array.from(document.querySelectorAll(${JSON.stringify(SAMPLE_DRAWER_CLOSE_SELECTOR)})).find(isVisible)
        if (!(closeNode instanceof HTMLElement)) {
          return false
        }
        ;['pointerdown', 'mousedown', 'pointerup', 'mouseup', 'click'].forEach((type) => {
          closeNode.dispatchEvent(new MouseEvent(type, { bubbles: true, cancelable: true, view: window }))
        })
        return true
      })()`
    )

    if (closed) {
      await this.waitForSelectorState(page, SAMPLE_DRAWER_SELECTOR, 'absent', 5000, 150)
    }
  }

  private emptyTabResult(tab: SampleManagementTabKey, stopReason: string): SampleManagementTabCrawlResult {
    return {
      tab,
      rows: [],
      pages_visited: 0,
      responses_captured: 0,
      stop_reason: stopReason,
      page_signatures: []
    }
  }

  private initializeWorkbook(): string {
    const exportDir = join(process.cwd(), 'data', 'sample-management')
    mkdirSync(exportDir, { recursive: true })

    const timestamp = this.buildTimestamp()
    const filePath = join(exportDir, `xunda_sample_management_${timestamp}.xlsx`)

    const workbook = XLSX.utils.book_new()
    this.appendSheet(workbook, TAB_CONFIG.to_review.sheetName, [], SAMPLE_MANAGEMENT_SHEET_COLUMNS.to_review)
    this.appendSheet(workbook, TAB_CONFIG.ready_to_ship.sheetName, [], SAMPLE_MANAGEMENT_SHEET_COLUMNS.ready_to_ship)
    this.appendSheet(workbook, TAB_CONFIG.shipped.sheetName, [], SAMPLE_MANAGEMENT_SHEET_COLUMNS.shipped)
    this.appendSheet(workbook, TAB_CONFIG.in_progress.sheetName, [], SAMPLE_MANAGEMENT_SHEET_COLUMNS.in_progress)
    this.appendSheet(workbook, TAB_CONFIG.completed.sheetName, [], SAMPLE_MANAGEMENT_SHEET_COLUMNS.completed)
    this.writeWorkbook(filePath, workbook)

    return filePath
  }

  private appendRowsToWorkbook(filePath: string, tab: SampleManagementTabKey, rows: SampleManagementRow[]): void {
    if (!rows.length) {
      return
    }

    const columns = SAMPLE_MANAGEMENT_SHEET_COLUMNS[tab]
    const sheetName = TAB_CONFIG[tab].sheetName
    const workbook = existsSync(filePath)
      ? XLSX.read(readFileSync(filePath), { type: 'buffer' })
      : XLSX.utils.book_new()
    const sheet = workbook.Sheets[sheetName] || XLSX.utils.aoa_to_sheet([columns as string[]])

    const orderedRows = rows.map((row) => this.toOrderedRow(row, columns))
    XLSX.utils.sheet_add_json(sheet, orderedRows, {
      header: columns as string[],
      skipHeader: true,
      origin: -1
    })

    workbook.Sheets[sheetName] = sheet
    if (!workbook.SheetNames.includes(sheetName)) {
      workbook.SheetNames.push(sheetName)
    }
    this.writeWorkbook(filePath, workbook)
  }

  private appendSheet(
    workbook: XLSX.WorkBook,
    sheetName: string,
    rows: SampleManagementRow[],
    columns: Array<keyof SampleManagementRow>
  ): void {
    const orderedRows = rows.map((row) => this.toOrderedRow(row, columns))

    const worksheet = XLSX.utils.json_to_sheet(orderedRows, {
      header: columns as string[]
    })
    XLSX.utils.book_append_sheet(workbook, worksheet, sheetName)
  }

  private toOrderedRow(
    row: SampleManagementRow,
    columns: Array<keyof SampleManagementRow>
  ): Record<string, string | number | null> {
    const current: Record<string, string | number | null> = {}
    columns.forEach((column) => {
      current[column] = row[column]
    })
    return current
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

  private writeWorkbook(filePath: string, workbook: XLSX.WorkBook): void {
    mkdirSync(dirname(filePath), { recursive: true })
    const buffer = XLSX.write(workbook, {
      type: 'buffer',
      bookType: 'xlsx'
    })
    writeFileSync(filePath, buffer)
  }
}
