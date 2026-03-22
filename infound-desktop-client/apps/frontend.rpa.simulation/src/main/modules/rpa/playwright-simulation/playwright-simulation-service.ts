import { existsSync, mkdirSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { randomUUID } from 'node:crypto'
import { readFile } from 'node:fs/promises'
import { chromium } from 'playwright'
import type { Browser, BrowserContext, Page } from 'playwright'
import type { SellerChatbotPayloadInput, SellerChatbotRecipient } from '@common/types/rpa-chatbot'
import type { SellerCreatorDetailData, SellerCreatorDetailPayloadInput } from '@common/types/rpa-creator-detail'
import type { OutreachFilterConfigInput } from '@common/types/rpa-outreach'
import type { SampleManagementPayloadInput } from '@common/types/rpa-sample-management'
import type { PlaywrightSimulationPayload, PlaywrightSimulationPayloadInput } from '@common/types/rpa-simulation'
import type { BrowserTask } from '../task-dsl/browser-actions'
import { BrowserActionRunner } from '../task-dsl/browser-action-runner'
import type { TaskLoggerLike } from '../task-dsl/types'
import {
  buildSellerCreatorDetailExtractionScript,
  persistSellerCreatorDetailArtifacts
} from '../creator-detail/extractor'
import {
  buildSellerCreatorDetailSteps,
  countCollectedCreatorDetailFields,
  createDemoSellerCreatorDetailPayload,
  mergeSellerCreatorDetailPayload
} from '../creator-detail/support'
import {
  buildSellerChatbotFinalizeSteps,
  buildSellerChatbotPrepareSteps,
  buildSellerChatbotSendAttemptSteps,
  createDemoSellerChatbotPayload,
  mergeSellerChatbotPayload,
  persistSellerChatbotSessionMarkdown,
  SELLER_CHATBOT_CREATOR_NAME_KEY,
  SELLER_CHATBOT_INPUT_COUNT_AFTER_KEY,
  SELLER_CHATBOT_INPUT_COUNT_KEY,
  SELLER_CHATBOT_INPUT_SELECTOR,
  SELLER_CHATBOT_MAX_SEND_ATTEMPTS,
  SELLER_CHATBOT_TRANSCRIPT_AFTER_KEY,
  SELLER_CHATBOT_TRANSCRIPT_BEFORE_KEY
} from '../chatbot/support'
import {
  buildOutreachFilterSteps,
  buildOutreachFilterStepsFromScript,
  createDemoOutreachFilterConfig,
  CREATOR_MARKETPLACE_DATA_KEY,
  CREATOR_MARKETPLACE_EXCEL_FILE_PATH_KEY,
  CREATOR_MARKETPLACE_FILE_PATH_KEY,
  CREATOR_MARKETPLACE_RAW_DIRECTORY_PATH_KEY,
  CREATOR_MARKETPLACE_RAW_FILE_PATH_KEY,
  isOutreachFilterScriptLike,
  mergeOutreachFilterConfig,
  resolveOutreachPageReadyText
} from '../outreach/support'
import { describeSampleManagementTabs, mergeSampleManagementPayload } from '../sample-management/support'
import type { SampleManagementExportResult } from '../sample-management/types'
import { PlaywrightBrowserActionTarget } from './playwright-browser-target'
import { PlaywrightJsonResponseCaptureManager } from './playwright-response-capture'
import { PlaywrightSampleManagementCrawler } from './sample-management-playwright'
import { evaluatePageScript } from './shared'
import { SellerRpaApiClient } from '../reporting/seller-rpa-api-client'
import { buildOutreachResultPayload } from '../reporting/seller-rpa-report-payloads'

const DEFAULT_REGION = 'MX'
const DEFAULT_STORAGE_STATE_PATH = join(process.cwd(), 'data', 'playwright', 'storage-state.json')
const PLAYWRIGHT_LOGIN_URL = 'https://seller-mx.tiktok.com/'
const SIMULATION_RUNTIME_ROLES = [
  'outreach',
  'creator_detail',
  'chatbot',
  'sample_management'
] as const

type SimulationRuntimeRole = (typeof SIMULATION_RUNTIME_ROLES)[number]

interface PlaywrightSimulationRuntime {
  role: SimulationRuntimeRole
  browser: Browser
  context: BrowserContext
  page: Page
  captureManager: PlaywrightJsonResponseCaptureManager
  target: PlaywrightBrowserActionTarget
  taskRunner: BrowserActionRunner
  sampleCrawler: PlaywrightSampleManagementCrawler
  payload: PlaywrightSimulationPayload
}

interface ChatbotSendResult {
  creatorId: string
  creatorName: string
  message: string
  send: 0 | 1
  sendTime?: string
  errorMessage?: string
}

export class PlaywrightSimulationService {
  private static instance: PlaywrightSimulationService | null = null

  public static getInstance(logger: TaskLoggerLike): PlaywrightSimulationService {
    if (!PlaywrightSimulationService.instance) {
      PlaywrightSimulationService.instance = new PlaywrightSimulationService(logger)
    }
    return PlaywrightSimulationService.instance
  }

  private runtimes = new Map<SimulationRuntimeRole, PlaywrightSimulationRuntime>()
  private taskChains = new Map<SimulationRuntimeRole, Promise<unknown>>()
  private activeTaskNames = new Map<SimulationRuntimeRole, string>()

  private constructor(private readonly logger: TaskLoggerLike) {}

  public hasActiveSession(): boolean {
    return this.runtimes.size === SIMULATION_RUNTIME_ROLES.length
  }

  public async startSession(input?: PlaywrightSimulationPayloadInput): Promise<void> {
    const payload = this.normalizePayload(input)

    if (this.runtimes.size > 0) {
      if (this.hasActiveTasks()) {
        throw new Error(
          `Playwright 会话正在执行任务，暂时不能重建。当前任务: ${this.buildActiveTaskSummary()}`
        )
      }

      if (this.areAllRuntimePayloadsSame(payload)) {
        await this.bringAllRuntimesToFront()
        this.logger.info(`Playwright 会话已存在，继续复用四个运行时: region=${payload.region}`)
        return
      }

      this.logger.info('检测到新的 Playwright 会话配置，正在重建四个浏览器会话')
      await this.dispose()
    }

    const createdRuntimes: PlaywrightSimulationRuntime[] = []
    try {
      for (const role of SIMULATION_RUNTIME_ROLES) {
        const runtime = await this.createRuntime(role, payload)
        this.runtimes.set(role, runtime)
        this.taskChains.set(role, Promise.resolve())
        createdRuntimes.push(runtime)
      }
      await this.bringAllRuntimesToFront()
      this.logger.info(
        `Playwright RPA 四运行时已启动: headless=${payload.headless ? 'true' : 'false'} region=${payload.region} roles=${SIMULATION_RUNTIME_ROLES.join(',')}`
      )
    } catch (error) {
      this.runtimes.clear()
      this.taskChains.clear()
      this.activeTaskNames.clear()
      await Promise.all(
        createdRuntimes.map(async (runtime) => {
          await runtime.context.close().catch(() => undefined)
          await runtime.browser.close().catch(() => undefined)
        })
      )
      throw error
    }
  }

  public async dispose(): Promise<void> {
    const runtimes = [...this.runtimes.values()]
    this.runtimes.clear()
    this.activeTaskNames.clear()
    this.taskChains.clear()

    if (!runtimes.length) return

    await Promise.all(
      runtimes.map(async (runtime) => {
        await runtime.context.close().catch(() => undefined)
        await runtime.browser.close().catch(() => undefined)
      })
    )
    this.logger.info('Playwright RPA 四运行时已关闭')
  }

  public async runOutreach(payload?: OutreachFilterConfigInput): Promise<void> {
    const effectivePayload = payload ?? createDemoOutreachFilterConfig()
    await this.ensureSession(this.buildSessionPayloadFromTaskContext(effectivePayload))
    await this.enqueueTask('outreach', 'outreach', async (runtime) => {
      const startedAt = new Date()
      const result = await this.runOutreachTask(
        runtime.taskRunner,
        runtime.payload.region,
        effectivePayload
      )
      const chatbotResults = await this.dispatchOutreachCreatorsToChatbot(
        runtime.payload.region,
        effectivePayload,
        result
      )
      this.mergeChatbotResultsIntoRuntimeData(result, chatbotResults)
      const finishedAt = new Date()
      const client = SellerRpaApiClient.create(this.logger, effectivePayload.report)
      if (!client) {
        this.logger.warn('建联任务未配置 seller backend 回传，跳过结果上报')
        return
      }

      const requestPayload = buildOutreachResultPayload(effectivePayload, result, {
        region: runtime.payload.region,
        startedAt,
        finishedAt
      })
      if (!requestPayload) {
        this.logger.warn('建联任务缺少 taskId/shopId，跳过结果上报')
        return
      }
      await client.reportOutreachResults(requestPayload)
    })
  }

  public async runSampleManagement(payload?: SampleManagementPayloadInput): Promise<void> {
    const effectivePayload = mergeSampleManagementPayload(payload)
    await this.ensureSession(this.buildSessionPayloadFromTaskContext(effectivePayload))
    await this.enqueueTask('sample_management', 'sample_management', async (runtime) => {
      await this.runSampleManagementTask(
        runtime.page,
        runtime.sampleCrawler,
        runtime.payload.region,
        effectivePayload.tabs
      )
    })
  }

  public async runChatbot(payload?: SellerChatbotPayloadInput): Promise<void> {
    const effectivePayload = payload ?? createDemoSellerChatbotPayload()
    await this.ensureSession(this.buildSessionPayloadFromTaskContext(effectivePayload))
    await this.enqueueTask('chatbot', 'chatbot', async (runtime) => {
      await this.runChatbotPayload(runtime.taskRunner, runtime.payload.region, effectivePayload)
    })
  }

  public async runCreatorDetail(payload?: SellerCreatorDetailPayloadInput): Promise<void> {
    const effectivePayload = payload ?? createDemoSellerCreatorDetailPayload()
    await this.ensureSession(this.buildSessionPayloadFromTaskContext(effectivePayload))
    await this.enqueueTask('creator_detail', 'creator_detail', async (runtime) => {
      await this.runCreatorDetailTask(
        runtime.taskRunner,
        runtime.page,
        runtime.payload.region,
        effectivePayload
      )
    })
  }

  private async enqueueTask<T>(
    role: SimulationRuntimeRole,
    taskName: string,
    handler: (runtime: PlaywrightSimulationRuntime) => Promise<T>
  ): Promise<T> {
    const previousChain = this.taskChains.get(role) ?? Promise.resolve()
    const runTask = previousChain.then(async () => {
      const runtime = this.requireRuntime(role)
      this.activeTaskNames.set(role, taskName)
      this.logger.info(`开始执行 Playwright 会话任务: role=${role} task=${taskName}`)
      try {
        const result = await handler(runtime)
        this.logger.info(`Playwright 会话任务执行完成: role=${role} task=${taskName}`)
        return result
      } finally {
        this.activeTaskNames.delete(role)
      }
    })

    this.taskChains.set(role, runTask.then(() => undefined, () => undefined))
    return runTask
  }

  private requireRuntime(role: SimulationRuntimeRole): PlaywrightSimulationRuntime {
    const runtime = this.runtimes.get(role)
    if (!runtime) {
      throw new Error('Playwright 会话尚未启动。请先点击“启动RPA模拟”或发送 RPA_EXECUTE_SIMULATION。')
    }
    return runtime
  }

  private async ensureSession(input?: PlaywrightSimulationPayloadInput): Promise<void> {
    if (this.hasActiveSession()) {
      return
    }
    await this.startSession(input)
  }

  private hasActiveTasks(): boolean {
    return this.activeTaskNames.size > 0
  }

  private buildActiveTaskSummary(): string {
    return [...this.activeTaskNames.entries()]
      .map(([role, taskName]) => `${role}:${taskName}`)
      .join(', ')
  }

  private areAllRuntimePayloadsSame(payload: PlaywrightSimulationPayload): boolean {
    if (!this.hasActiveSession()) {
      return false
    }
    return SIMULATION_RUNTIME_ROLES.every((role) => {
      const runtime = this.runtimes.get(role)
      return runtime ? this.isSameSessionPayload(runtime.payload, payload) : false
    })
  }

  private async bringAllRuntimesToFront(): Promise<void> {
    for (const role of SIMULATION_RUNTIME_ROLES) {
      const runtime = this.runtimes.get(role)
      if (!runtime) {
        continue
      }
      await runtime.page.bringToFront().catch(() => undefined)
    }
  }

  private async createRuntime(
    role: SimulationRuntimeRole,
    payload: PlaywrightSimulationPayload
  ): Promise<PlaywrightSimulationRuntime> {
    const browser = await chromium.launch({
      headless: payload.headless
    })

    try {
      const contextOptions: Parameters<Browser['newContext']>[0] = {
        viewport: { width: 1440, height: 900 }
      }
      if (payload.useStorageState) {
        contextOptions.storageState = payload.storageStatePath
      }

      const context = await browser.newContext(contextOptions)
      const page = await context.newPage()
      const captureManager = new PlaywrightJsonResponseCaptureManager(this.logger)
      const target = new PlaywrightBrowserActionTarget(page, this.logger, captureManager)
      const taskRunner = new BrowserActionRunner(this.logger, target)
      const sampleCrawler = new PlaywrightSampleManagementCrawler()
      const idleUrl = this.buildRuntimeIdleUrl(role, payload.region)
      const bootUrl = payload.useStorageState ? idleUrl : PLAYWRIGHT_LOGIN_URL

      await page.goto(bootUrl, { waitUntil: 'domcontentloaded' })
      await page.bringToFront().catch(() => undefined)

      if (payload.useStorageState) {
        this.logger.info(
          `Playwright 运行时已启动: role=${role} headless=${payload.headless ? 'true' : 'false'} region=${payload.region} idle=${idleUrl}`
        )
      } else {
        this.logger.warn(
          `找不到 storage state，已启动手动登录运行时: role=${role} headless=${payload.headless ? 'true' : 'false'} region=${payload.region} login=${PLAYWRIGHT_LOGIN_URL}`
        )
      }

      return {
        role,
        browser,
        context,
        page,
        captureManager,
        target,
        taskRunner,
        sampleCrawler,
        payload
      }
    } catch (error) {
      await browser.close().catch(() => undefined)
      throw error
    }
  }

  private buildRuntimeIdleUrl(role: SimulationRuntimeRole, region: string): string {
    switch (role) {
      case 'outreach':
        return `https://affiliate.tiktok.com/connection/creator?shop_region=${encodeURIComponent(region)}`
      case 'sample_management':
        return `https://affiliate.tiktok.com/product/sample-request?shop_region=${encodeURIComponent(region)}`
      case 'chatbot':
      case 'creator_detail':
      default:
        return this.buildIdleUrl(region)
    }
  }

  private buildSessionPayloadFromTaskContext(context?: {
    shopRegionCode?: string
  }): PlaywrightSimulationPayloadInput {
    return {
      region: String(context?.shopRegionCode || DEFAULT_REGION).trim().toUpperCase() || DEFAULT_REGION
    }
  }

  private normalizePayload(input?: PlaywrightSimulationPayloadInput): PlaywrightSimulationPayload {
    const region = String(input?.region || DEFAULT_REGION).trim().toUpperCase() || DEFAULT_REGION
    const requestedHeadless = Boolean(input?.headless ?? false)
    const storageStatePath = resolve(String(input?.storageStatePath || DEFAULT_STORAGE_STATE_PATH).trim())
    const useStorageState = existsSync(storageStatePath)
    let headless = requestedHeadless

    if (!useStorageState) {
      const parentDir = dirname(storageStatePath)
      mkdirSync(parentDir, { recursive: true })
      if (requestedHeadless) {
        headless = false
        this.logger.warn(`未找到 Playwright storage state，无法在无头模式下手动登录，已自动切换为有头模式。`)
      }
      this.logger.warn(`未找到 Playwright storage state: ${storageStatePath}，将直接打开登录页面等待手动操作。`)
    }

    return {
      region,
      headless,
      storageStatePath,
      useStorageState
    }
  }

  private buildIdleUrl(region: string): string {
    return `https://affiliate.tiktok.com/platform/homepage?shop_region=${encodeURIComponent(region)}`
  }

  private isSameSessionPayload(a: PlaywrightSimulationPayload, b: PlaywrightSimulationPayload): boolean {
    return (
      a.region === b.region &&
      a.headless === b.headless &&
      a.storageStatePath === b.storageStatePath &&
      a.useStorageState === b.useStorageState
    )
  }

  private async runOutreachTask(
    taskRunner: BrowserActionRunner,
    region: string,
    payload?: OutreachFilterConfigInput
  ): Promise<Record<string, unknown>> {
    const filterConfig = mergeOutreachFilterConfig(payload)
    const externalFilterScript = await this.resolveOutreachFilterScript(payload)
    const pageReadyText = resolveOutreachPageReadyText(externalFilterScript)
    const filterSteps =
      buildOutreachFilterStepsFromScript(filterConfig, externalFilterScript) ||
      buildOutreachFilterSteps(filterConfig)
    const targetUrl = `https://affiliate.tiktok.com/connection/creator?shop_region=${encodeURIComponent(region)}`

    const taskData = {
      taskId: randomUUID(),
      taskName: '建联任务(Playwright)',
      version: '1.0.0',
      config: {
        enableTrace: true,
        retryCount: 0
      },
      steps: [
        {
          actionType: 'goto',
          payload: {
            url: targetUrl,
            postLoadWaitMs: 2500
          },
          options: { retryCount: 1 },
          onError: 'abort'
        },
        {
          actionType: 'waitForBodyText',
          payload: {
            text: pageReadyText,
            timeoutMs: 30000,
            intervalMs: 500
          },
          recovery: {
            gotoUrl: targetUrl,
            postLoadWaitMs: 2500
          },
          options: { retryCount: 5 },
          onError: 'abort'
        },
        ...filterSteps
      ]
    } as BrowserTask

    if (externalFilterScript) {
      this.logger.info(
        `[${taskData.taskId}] 建联任务使用外部筛选脚本: region=${region} source=task-input`
      )
    } else {
      this.logger.info(
        `[${taskData.taskId}] 建联任务使用内置筛选脚本: region=${region} source=fallback`
      )
    }
    this.logger.info(`[${taskData.taskId}] 启动建联任务(Playwright): region=${region} steps=${taskData.steps.length}`)

    const runtimeData = (await taskRunner.execute(taskData)) as Record<string, unknown>
    const creatorCount = Array.isArray(runtimeData[CREATOR_MARKETPLACE_DATA_KEY])
      ? runtimeData[CREATOR_MARKETPLACE_DATA_KEY].length
      : 0
    const filePath = String(runtimeData[CREATOR_MARKETPLACE_FILE_PATH_KEY] || '')
    const excelFilePath = String(runtimeData[CREATOR_MARKETPLACE_EXCEL_FILE_PATH_KEY] || '')
    const rawFilePath = String(runtimeData[CREATOR_MARKETPLACE_RAW_FILE_PATH_KEY] || '')
    const rawDirectoryPath = String(runtimeData[CREATOR_MARKETPLACE_RAW_DIRECTORY_PATH_KEY] || '')

    this.logger.info(
      `[${taskData.taskId}] 建联任务执行完成(Playwright): creators=${creatorCount}${filePath ? ` file=${filePath}` : ''}${excelFilePath ? ` excel=${excelFilePath}` : ''}${rawFilePath ? ` raw_file=${rawFilePath}` : ''}${rawDirectoryPath ? ` raw_dir=${rawDirectoryPath}` : ''}`
    )
    return runtimeData
  }

  private async resolveOutreachFilterScript(
    payload?: OutreachFilterConfigInput
  ): Promise<Record<string, unknown> | null> {
    const inlineScript =
      payload?.filterScript && typeof payload.filterScript === 'object'
        ? payload.filterScript
        : null
    if (isOutreachFilterScriptLike(inlineScript)) {
      return inlineScript
    }

    const candidatePath =
      (typeof payload?.filterScript === 'string' ? payload.filterScript : '') ||
      String(payload?.filterScriptPath || '').trim()
    if (!candidatePath) {
      return null
    }

    const resolvedPath = this.resolveTaskJsonPath(candidatePath)
    const fileContent = await readFile(resolvedPath, 'utf8')
    const parsed = JSON.parse(fileContent) as unknown
    if (!isOutreachFilterScriptLike(parsed)) {
      throw new Error(`建联外部筛选脚本格式不正确: ${resolvedPath}`)
    }
    return parsed
  }

  private resolveTaskJsonPath(inputPath: string): string {
    const trimmedPath = String(inputPath || '').trim()
    if (!trimmedPath) {
      throw new Error('建联外部筛选脚本路径为空')
    }

    const candidatePaths = new Set<string>()
    if (trimmedPath.startsWith('{') || trimmedPath.startsWith('[')) {
      throw new Error('建联外部筛选脚本路径不能是内联 JSON 字符串')
    }
    if (trimmedPath.startsWith('/')) {
      candidatePaths.add(trimmedPath)
    } else {
      candidatePaths.add(resolve(process.cwd(), trimmedPath))
      candidatePaths.add(resolve(process.cwd(), '..', trimmedPath))
      candidatePaths.add(resolve(process.cwd(), '..', '..', trimmedPath))
      candidatePaths.add(resolve(process.cwd(), '..', '..', '..', trimmedPath))
    }

    for (const candidatePath of candidatePaths) {
      if (existsSync(candidatePath)) {
        return candidatePath
      }
    }

    throw new Error(`找不到建联外部筛选脚本文件: ${trimmedPath}`)
  }

  private resolveOutreachMessage(payload?: OutreachFilterConfigInput): string {
    return String(payload?.message ?? payload?.firstMessage ?? '').trim()
  }

  private buildOutreachChatRecipients(
    payload: OutreachFilterConfigInput,
    runtimeData: Record<string, unknown>
  ): SellerChatbotRecipient[] {
    const message = this.resolveOutreachMessage(payload)
    if (!message) {
      return []
    }

    const rawItems = runtimeData[CREATOR_MARKETPLACE_DATA_KEY]
    if (!Array.isArray(rawItems)) {
      return []
    }

    const recipients: SellerChatbotRecipient[] = []
    const seenCreatorIds = new Set<string>()
    for (const rawItem of rawItems) {
      if (!rawItem || typeof rawItem !== 'object' || Array.isArray(rawItem)) {
        continue
      }
      const item = rawItem as Record<string, unknown>
      const creatorId = String(item.creator_id ?? item.platform_creator_id ?? '').trim()
      if (!creatorId || seenCreatorIds.has(creatorId)) {
        continue
      }
      recipients.push({
        creatorId,
        message
      })
      seenCreatorIds.add(creatorId)
    }
    return recipients
  }

  private async dispatchOutreachCreatorsToChatbot(
    region: string,
    payload: OutreachFilterConfigInput,
    runtimeData: Record<string, unknown>
  ): Promise<ChatbotSendResult[]> {
    const message = this.resolveOutreachMessage(payload)
    if (!message) {
      this.logger.info('[outreach->chatbot] 建联任务未配置 message/firstMessage，跳过自动聊天')
      return []
    }

    const recipients = this.buildOutreachChatRecipients(payload, runtimeData)
    if (!recipients.length) {
      this.logger.warn('[outreach->chatbot] 建联任务未采集到可发送聊天的达人，跳过自动聊天')
      return []
    }

    this.logger.info(
      `[outreach->chatbot] 建联任务准备移交聊天机器人: creators=${recipients.length} region=${region}`
    )
    return this.enqueueTask('chatbot', 'chatbot_from_outreach', async (runtime) =>
      this.runChatbotPayload(runtime.taskRunner, runtime.payload.region, {
        ...payload,
        creatorId: recipients[0]?.creatorId ?? '',
        message,
        recipients
      })
    )
  }

  private mergeChatbotResultsIntoRuntimeData(
    runtimeData: Record<string, unknown>,
    chatbotResults: ChatbotSendResult[]
  ): void {
    const rawItems = runtimeData[CREATOR_MARKETPLACE_DATA_KEY]
    if (!Array.isArray(rawItems)) {
      return
    }

    const resultMap = new Map(chatbotResults.map((item) => [item.creatorId, item] as const))
    for (const rawItem of rawItems) {
      if (!rawItem || typeof rawItem !== 'object' || Array.isArray(rawItem)) {
        continue
      }
      const item = rawItem as Record<string, unknown>
      const creatorId = String(item.creator_id ?? item.platform_creator_id ?? '').trim()
      const sendResult = creatorId ? resultMap.get(creatorId) : undefined
      item.send = sendResult?.send ?? 0
      if (sendResult?.sendTime) {
        item.send_time = sendResult.sendTime
      }
    }
  }

  private resolveChatbotRecipients(payload: {
    creatorId?: string
    message?: string
    recipients?: SellerChatbotRecipient[]
  }): SellerChatbotRecipient[] {
    const recipients = Array.isArray(payload.recipients)
      ? payload.recipients
          .map((item) => ({
            creatorId: String(item.creatorId ?? '').trim(),
            message: String(item.message ?? '').trim() || undefined
          }))
          .filter((item) => Boolean(item.creatorId))
      : []

    if (recipients.length) {
      return recipients
    }

    const creatorId = String(payload.creatorId ?? '').trim()
    if (!creatorId) {
      return []
    }

    return [
      {
        creatorId,
        message: String(payload.message ?? '').trim() || undefined
      }
    ]
  }

  private async runSampleManagementTask(
    page: Page,
    sampleCrawler: PlaywrightSampleManagementCrawler,
    region: string,
    tabs: ReturnType<typeof mergeSampleManagementPayload>['tabs']
  ): Promise<SampleManagementExportResult> {
    const targetUrl = `https://affiliate.tiktok.com/product/sample-request?shop_region=${encodeURIComponent(region)}`
    this.logger.info(`跳转样品管理页面(Playwright): ${targetUrl}`)
    let currentUrl = ''
    let opened = false

    for (let attempt = 1; attempt <= 2; attempt += 1) {
      await page.goto(targetUrl, { waitUntil: 'domcontentloaded' })
      await page.bringToFront().catch(() => undefined)
      const reachedTargetUrl = await page
        .waitForURL(/\/product\/sample-request(\?|$)/, { timeout: 30000 })
        .then(() => true)
        .catch(() => false)
      await page.waitForLoadState('domcontentloaded').catch(() => undefined)
      await new Promise((resolve) => setTimeout(resolve, 1200))
      currentUrl = page.url()
      this.logger.info(
        `样品管理页面当前 URL(Playwright): attempt=${attempt} reached_target=${reachedTargetUrl} url=${currentUrl}`
      )
      if (currentUrl.includes('/product/sample-request')) {
        opened = true
        break
      }
      this.logger.warn(`样品管理页面跳转未命中目标，准备重试(Playwright): attempt=${attempt} current_url=${currentUrl}`)
    }

    if (!opened) {
      throw new Error(`样品管理页面未成功打开，当前 URL=${currentUrl}`)
    }
    this.logger.info(`样品管理任务指定 tabs(Playwright): ${describeSampleManagementTabs(tabs)}`)
    const result = await sampleCrawler.crawlTabsAndExportExcel(page, {
      tabs
    })
    this.logger.info(`样品管理任务执行完成(Playwright): excel=${result.excel_path}`)
    return result
  }

  private async runChatbotPayload(
    taskRunner: BrowserActionRunner,
    region: string,
    payload?: SellerChatbotPayloadInput
  ): Promise<ChatbotSendResult[]> {
    const chatbotPayload = mergeSellerChatbotPayload(payload)
    const recipients = this.resolveChatbotRecipients(chatbotPayload)
    if (!recipients.length) {
      throw new Error('聊天机器人缺少 creatorId 或 recipients')
    }

    if (recipients.length === 1) {
      const recipient = recipients[0]
      return [
        await this.runChatbotTask(taskRunner, region, {
          ...chatbotPayload,
          recipients: undefined,
          creatorId: recipient.creatorId,
          message: recipient.message ?? chatbotPayload.message
        })
      ]
    }

    const results: ChatbotSendResult[] = []
    for (const recipient of recipients) {
      const message = String(recipient.message ?? chatbotPayload.message).trim()
      if (!message) {
        results.push({
          creatorId: recipient.creatorId,
          creatorName: '',
          message,
          send: 0,
          errorMessage: '聊天机器人缺少 message'
        })
        continue
      }

      try {
        const result = await this.runChatbotTask(taskRunner, region, {
          ...chatbotPayload,
          recipients: undefined,
          creatorId: recipient.creatorId,
          message
        })
        results.push(result)
      } catch (error) {
        const errorMessage = (error as Error)?.message || String(error)
        this.logger.error(
          `[chatbot-batch] 聊天消息发送失败(Playwright): creator_id=${recipient.creatorId} error=${errorMessage}`
        )
        results.push({
          creatorId: recipient.creatorId,
          creatorName: '',
          message,
          send: 0,
          errorMessage
        })
      }
    }

    if (results.every((item) => item.send !== 1)) {
      throw new Error('聊天机器人批量任务全部失败')
    }
    return results
  }

  private async runChatbotTask(
    taskRunner: BrowserActionRunner,
    region: string,
    payload?: SellerChatbotPayloadInput
  ): Promise<ChatbotSendResult> {
    const chatbotPayload = mergeSellerChatbotPayload(payload)
    if (!chatbotPayload.creatorId) {
      throw new Error('聊天机器人缺少 creatorId')
    }
    if (!chatbotPayload.message) {
      throw new Error('聊天机器人缺少 message')
    }

    const targetUrl = `https://affiliate.tiktok.com/seller/im?creator_id=${encodeURIComponent(chatbotPayload.creatorId)}&shop_region=${encodeURIComponent(region)}`

    const taskData = {
      taskId: randomUUID(),
      taskName: '聊天机器人任务(Playwright)',
      version: '1.0.0',
      config: {
        enableTrace: true,
        retryCount: 0
      },
      steps: [
        {
          actionType: 'goto',
          payload: {
            url: targetUrl,
            postLoadWaitMs: 2500
          },
          options: { retryCount: 1 },
          onError: 'abort'
        },
        {
          actionType: 'waitForSelector',
          payload: {
            selector: SELLER_CHATBOT_INPUT_SELECTOR,
            state: 'visible',
            timeoutMs: 30000,
            intervalMs: 500
          },
          recovery: {
            gotoUrl: targetUrl,
            postLoadWaitMs: 2500
          },
          options: { retryCount: 5 },
          onError: 'abort'
        },
        ...buildSellerChatbotPrepareSteps()
      ]
    } as BrowserTask

    const initialRuntimeData = await taskRunner.execute(taskData)
    const creatorName = String(initialRuntimeData[SELLER_CHATBOT_CREATOR_NAME_KEY] || '')
    const transcriptBefore = String(initialRuntimeData[SELLER_CHATBOT_TRANSCRIPT_BEFORE_KEY] || '')

    let sendVerified = false
    let sendAttempts = 0
    let sendTime: string | undefined

    for (let attempt = 1; attempt <= SELLER_CHATBOT_MAX_SEND_ATTEMPTS; attempt += 1) {
      sendAttempts = attempt
      const sendTaskData = {
        taskId: randomUUID(),
        taskName: `聊天机器人发送尝试 #${attempt}(Playwright)`,
        version: '1.0.0',
        config: {
          enableTrace: true,
          retryCount: 0
        },
        steps: buildSellerChatbotSendAttemptSteps(chatbotPayload.message)
      } as BrowserTask

      const sendRuntimeData = await taskRunner.execute(sendTaskData)
      const inputCount = String(sendRuntimeData[SELLER_CHATBOT_INPUT_COUNT_KEY] || '')
      const inputCountAfter = String(sendRuntimeData[SELLER_CHATBOT_INPUT_COUNT_AFTER_KEY] || '')

      if (inputCount && inputCount !== '0' && inputCountAfter === '0') {
        sendVerified = true
        sendTime = new Date().toISOString()
        this.logger.info(
          `[${taskData.taskId}] 聊天消息发送校验通过(Playwright): creator_id=${chatbotPayload.creatorId} attempt=${attempt} input_count=${inputCount} input_count_after=${inputCountAfter}`
        )
        break
      }

      this.logger.warn(
        `[${taskData.taskId}] 聊天消息发送校验失败(Playwright): creator_id=${chatbotPayload.creatorId} attempt=${attempt} input_count=${inputCount || '(empty)'} input_count_after=${inputCountAfter || '(empty)'}`
      )
    }

    if (!sendVerified) {
      throw new Error(`聊天消息发送校验失败: creator_id=${chatbotPayload.creatorId}`)
    }

    const finalizeTaskData = {
      taskId: randomUUID(),
      taskName: '聊天机器人收尾任务(Playwright)',
      version: '1.0.0',
      config: {
        enableTrace: true,
        retryCount: 0
      },
      steps: buildSellerChatbotFinalizeSteps()
    } as BrowserTask

    const finalizeRuntimeData = await taskRunner.execute(finalizeTaskData)
    const transcriptAfter = String(finalizeRuntimeData[SELLER_CHATBOT_TRANSCRIPT_AFTER_KEY] || '')

    const sessionMarkdownPath = persistSellerChatbotSessionMarkdown({
      creatorId: chatbotPayload.creatorId,
      region,
      targetUrl,
      creatorName,
      message: chatbotPayload.message,
      transcriptBefore,
      transcriptAfter,
      sendVerified,
      sendAttempts
    })

    this.logger.info(
      `[${taskData.taskId}] 聊天机器人任务执行完成(Playwright): creator_id=${chatbotPayload.creatorId}${creatorName ? ` creator_name=${creatorName}` : ''} attempts=${sendAttempts} md=${sessionMarkdownPath}`
    )
    return {
      creatorId: chatbotPayload.creatorId,
      creatorName,
      message: chatbotPayload.message,
      send: sendVerified ? 1 : 0,
      sendTime
    }
  }

  private async runCreatorDetailTask(
    taskRunner: BrowserActionRunner,
    page: Page,
    region: string,
    payload?: SellerCreatorDetailPayloadInput
  ): Promise<SellerCreatorDetailData> {
    const creatorDetailPayload = mergeSellerCreatorDetailPayload(payload)
    if (!creatorDetailPayload.creatorId) {
      throw new Error('达人详情机器人缺少 creatorId')
    }

    const targetUrl = `https://affiliate.tiktok.com/connection/creator/detail?cid=${encodeURIComponent(creatorDetailPayload.creatorId)}&shop_region=${encodeURIComponent(region)}`
    const taskData = {
      taskId: randomUUID(),
      taskName: '达人详细信息爬取任务(Playwright)',
      version: '1.0.0',
      config: {
        enableTrace: true,
        retryCount: 0
      },
      steps: [
        {
          actionType: 'goto',
          payload: {
            url: targetUrl,
            postLoadWaitMs: 2500
          },
          options: { retryCount: 1 },
          onError: 'abort'
        },
        {
          actionType: 'assertUrlContains',
          payload: {
            keyword: '/connection/creator/detail'
          },
          options: { retryCount: 2 },
          onError: 'abort'
        },
        ...buildSellerCreatorDetailSteps()
      ]
    } as BrowserTask

    await taskRunner.execute(taskData)

    let detail: SellerCreatorDetailData | null = null
    for (let attempt = 1; attempt <= 3; attempt += 1) {
      const extracted = await evaluatePageScript<SellerCreatorDetailData>(page, buildSellerCreatorDetailExtractionScript())
      detail = {
        ...extracted,
        creator_id: extracted?.creator_id || creatorDetailPayload.creatorId,
        region: extracted?.region || region,
        target_url: extracted?.target_url || targetUrl,
        collected_at_utc: extracted?.collected_at_utc || new Date().toISOString(),
        creator_name: extracted?.creator_name || '',
        creator_rating: extracted?.creator_rating || '',
        creator_review_count: extracted?.creator_review_count || '',
        creator_followers_count: extracted?.creator_followers_count || '',
        creator_mcn: extracted?.creator_mcn || '',
        creator_intro: extracted?.creator_intro || '',
        gmv: extracted?.gmv || '',
        items_sold: extracted?.items_sold || '',
        gpm: extracted?.gpm || '',
        gmv_per_customer: extracted?.gmv_per_customer || '',
        est_post_rate: extracted?.est_post_rate || '',
        avg_commission_rate: extracted?.avg_commission_rate || '',
        products: extracted?.products || '',
        brand_collaborations: extracted?.brand_collaborations || '',
        brands_list: extracted?.brands_list || '',
        product_price: extracted?.product_price || '',
        video_gpm: extracted?.video_gpm || '',
        videos_count: extracted?.videos_count || '',
        avg_video_views: extracted?.avg_video_views || '',
        avg_video_engagement: extracted?.avg_video_engagement || '',
        avg_video_likes: extracted?.avg_video_likes || '',
        avg_video_comments: extracted?.avg_video_comments || '',
        avg_video_shares: extracted?.avg_video_shares || '',
        live_gpm: extracted?.live_gpm || '',
        live_streams: extracted?.live_streams || '',
        avg_live_views: extracted?.avg_live_views || '',
        avg_live_engagement: extracted?.avg_live_engagement || '',
        avg_live_likes: extracted?.avg_live_likes || '',
        avg_live_comments: extracted?.avg_live_comments || '',
        avg_live_shares: extracted?.avg_live_shares || '',
        gmv_per_sales_channel: extracted?.gmv_per_sales_channel || {},
        gmv_by_product_category: extracted?.gmv_by_product_category || {},
        follower_gender: extracted?.follower_gender || {},
        follower_age: extracted?.follower_age || {},
        videos_list: extracted?.videos_list || [],
        videos_with_product: extracted?.videos_with_product || [],
        relative_creators: extracted?.relative_creators || []
      }

      if (detail.creator_name) {
        break
      }

      this.logger.warn(
        `[${taskData.taskId}] 达人详情提取重试(Playwright): creator_id=${creatorDetailPayload.creatorId} attempt=${attempt}`
      )
      await page.waitForTimeout(1000)
    }

    if (!detail?.creator_name) {
      throw new Error(`达人详情提取失败: creator_id=${creatorDetailPayload.creatorId}`)
    }

    const { jsonPath, csvPath } = persistSellerCreatorDetailArtifacts(detail)
    const collectedFieldCount = countCollectedCreatorDetailFields(detail)

    this.logger.info(
      `[${taskData.taskId}] 达人详细信息页采集完成(Playwright): creator_id=${creatorDetailPayload.creatorId} creator_name=${detail.creator_name} fields=${collectedFieldCount} json=${jsonPath} csv=${csvPath}`
    )
    return detail
  }
}
