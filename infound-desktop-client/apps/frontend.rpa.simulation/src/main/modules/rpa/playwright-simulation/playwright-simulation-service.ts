import { existsSync, mkdirSync } from 'node:fs'
import { dirname, join, resolve } from 'node:path'
import { randomUUID } from 'node:crypto'
import { chromium } from 'playwright'
import type { Browser, BrowserContext, Page } from 'playwright'
import type { SellerChatbotPayloadInput } from '@common/types/rpa-chatbot'
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
  createDemoOutreachFilterConfig,
  CREATOR_MARKETPLACE_DATA_KEY,
  CREATOR_MARKETPLACE_EXCEL_FILE_PATH_KEY,
  CREATOR_MARKETPLACE_FILE_PATH_KEY,
  CREATOR_MARKETPLACE_RAW_DIRECTORY_PATH_KEY,
  CREATOR_MARKETPLACE_RAW_FILE_PATH_KEY,
  mergeOutreachFilterConfig
} from '../outreach/support'
import { describeSampleManagementTabs, mergeSampleManagementPayload } from '../sample-management/support'
import type { SampleManagementExportResult } from '../sample-management/types'
import { PlaywrightBrowserActionTarget } from './playwright-browser-target'
import { PlaywrightJsonResponseCaptureManager } from './playwright-response-capture'
import { PlaywrightSampleManagementCrawler } from './sample-management-playwright'
import { evaluatePageScript } from './shared'
import { SellerRpaApiClient } from '../reporting/seller-rpa-api-client'
import {
  buildCreatorDetailResultPayload,
  buildOutreachResultPayload,
  buildSampleMonitorResultPayload
} from '../reporting/seller-rpa-report-payloads'

const DEFAULT_REGION = 'MX'
const DEFAULT_STORAGE_STATE_PATH = join(process.cwd(), 'data', 'playwright', 'storage-state.json')
const PLAYWRIGHT_LOGIN_URL = 'https://seller-mx.tiktok.com/'

interface PlaywrightSimulationRuntime {
  browser: Browser
  context: BrowserContext
  page: Page
  captureManager: PlaywrightJsonResponseCaptureManager
  target: PlaywrightBrowserActionTarget
  taskRunner: BrowserActionRunner
  sampleCrawler: PlaywrightSampleManagementCrawler
  payload: PlaywrightSimulationPayload
}

export class PlaywrightSimulationService {
  private static instance: PlaywrightSimulationService | null = null

  public static getInstance(logger: TaskLoggerLike): PlaywrightSimulationService {
    if (!PlaywrightSimulationService.instance) {
      PlaywrightSimulationService.instance = new PlaywrightSimulationService(logger)
    }
    return PlaywrightSimulationService.instance
  }

  private runtime: PlaywrightSimulationRuntime | null = null
  private taskChain: Promise<void> = Promise.resolve()
  private activeTaskName: string | null = null

  private constructor(private readonly logger: TaskLoggerLike) {}

  public hasActiveSession(): boolean {
    return this.runtime != null
  }

  public async startSession(input?: PlaywrightSimulationPayloadInput): Promise<void> {
    const payload = this.normalizePayload(input)

    if (this.runtime) {
      if (this.activeTaskName) {
        throw new Error(`Playwright 会话正在执行任务，暂时不能重建。当前任务: ${this.activeTaskName}`)
      }

      if (this.isSameSessionPayload(this.runtime.payload, payload)) {
        await this.runtime.page.bringToFront().catch(() => undefined)
        this.logger.info(`Playwright 会话已存在，继续复用: ${this.buildIdleUrl(payload.region)}`)
        return
      }

      this.logger.info('检测到新的 Playwright 会话配置，正在重建浏览器会话')
      await this.dispose()
    }

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
      const idleUrl = this.buildIdleUrl(payload.region)
      const bootUrl = payload.useStorageState ? idleUrl : PLAYWRIGHT_LOGIN_URL

      await page.goto(bootUrl, { waitUntil: 'domcontentloaded' })
      await page.bringToFront().catch(() => undefined)

      this.runtime = {
        browser,
        context,
        page,
        captureManager,
        target,
        taskRunner,
        sampleCrawler,
        payload
      }

      if (payload.useStorageState) {
        this.logger.info(
          `Playwright RPA 模拟会话已启动: headless=${payload.headless ? 'true' : 'false'} region=${payload.region} idle=${idleUrl}`
        )
      } else {
        this.logger.warn(
          `找不到 storage state，已启动手动登录会话: headless=${payload.headless ? 'true' : 'false'} region=${payload.region} login=${PLAYWRIGHT_LOGIN_URL}`
        )
      }
    } catch (error) {
      await browser.close().catch(() => undefined)
      throw error
    }
  }

  public async dispose(): Promise<void> {
    const runtime = this.runtime
    this.runtime = null
    this.activeTaskName = null
    this.taskChain = Promise.resolve()

    if (!runtime) return

    await runtime.context.close().catch(() => undefined)
    await runtime.browser.close().catch(() => undefined)
    this.logger.info('Playwright RPA 模拟会话已关闭')
  }

  public async runOutreach(payload?: OutreachFilterConfigInput): Promise<void> {
    const effectivePayload = payload ?? createDemoOutreachFilterConfig()
    await this.enqueueTask('outreach', async (runtime) => {
      await this.executeWithReporting<Record<string, unknown>>({
        taskLabel: 'outreach',
        taskId: effectivePayload.taskId,
        reportConfig: effectivePayload.report,
        run: async () =>
          await this.runOutreachTask(runtime.taskRunner, runtime.payload.region, effectivePayload),
        onSuccess: async (client, meta, result) => {
          const requestPayload = buildOutreachResultPayload(effectivePayload, result, {
            region: runtime.payload.region,
            startedAt: meta.startedAt,
            finishedAt: meta.finishedAt
          })
          if (!requestPayload) {
            this.logger.warn('建联任务缺少 taskId/shopId，跳过结果上报')
            return
          }
          await client.reportOutreachResults(requestPayload)
        }
      })
    })
  }

  public async runSampleManagement(payload?: SampleManagementPayloadInput): Promise<void> {
    const effectivePayload = mergeSampleManagementPayload(payload)
    await this.enqueueTask('sample_management', async (runtime) => {
      await this.executeWithReporting<SampleManagementExportResult>({
        taskLabel: 'sample_management',
        taskId: effectivePayload.taskId,
        reportConfig: effectivePayload.report,
        run: async () =>
          await this.runSampleManagementTask(
            runtime.page,
            runtime.sampleCrawler,
            runtime.payload.region,
            effectivePayload.tabs
          ),
        onSuccess: async (client, meta, result) => {
          const requestPayload = buildSampleMonitorResultPayload(effectivePayload, result, {
            region: runtime.payload.region,
            startedAt: meta.startedAt,
            finishedAt: meta.finishedAt
          })
          if (!requestPayload) {
            this.logger.warn('样品管理任务缺少 shopId，跳过结果上报')
            return
          }
          await client.reportSampleMonitorResults(requestPayload)
        }
      })
    })
  }

  public async runChatbot(payload?: SellerChatbotPayloadInput): Promise<void> {
    const effectivePayload = payload ?? createDemoSellerChatbotPayload()
    await this.enqueueTask('chatbot', async (runtime) => {
      await this.executeWithReporting<void>({
        taskLabel: 'chatbot',
        taskId: effectivePayload.taskId,
        reportConfig: effectivePayload.report,
        run: async () =>
          await this.runChatbotTask(runtime.taskRunner, runtime.payload.region, effectivePayload)
      })
    })
  }

  public async runCreatorDetail(payload?: SellerCreatorDetailPayloadInput): Promise<void> {
    const effectivePayload = payload ?? createDemoSellerCreatorDetailPayload()
    await this.enqueueTask('creator_detail', async (runtime) => {
      await this.executeWithReporting<SellerCreatorDetailData>({
        taskLabel: 'creator_detail',
        taskId: effectivePayload.taskId,
        reportConfig: effectivePayload.report,
        run: async () =>
          await this.runCreatorDetailTask(
            runtime.taskRunner,
            runtime.page,
            runtime.payload.region,
            effectivePayload
          ),
        onSuccess: async (client, meta, result) => {
          const requestPayload = buildCreatorDetailResultPayload(effectivePayload, result, {
            region: runtime.payload.region,
            startedAt: meta.startedAt,
            finishedAt: meta.finishedAt
          })
          if (!requestPayload) {
            this.logger.warn('达人详情任务缺少 shopId，跳过结果上报')
            return
          }
          await client.reportCreatorDetailResults(requestPayload)
        }
      })
    })
  }

  private async enqueueTask(
    taskName: 'outreach' | 'sample_management' | 'chatbot' | 'creator_detail',
    handler: (runtime: PlaywrightSimulationRuntime) => Promise<void>
  ): Promise<void> {
    const runTask = this.taskChain.then(async () => {
      const runtime = this.requireRuntime()
      this.activeTaskName = taskName
      this.logger.info(`开始执行 Playwright 会话任务: ${taskName}`)
      try {
        await handler(runtime)
        this.logger.info(`Playwright 会话任务执行完成: ${taskName}`)
      } finally {
        this.activeTaskName = null
      }
    })

    this.taskChain = runTask.catch(() => undefined)
    return runTask
  }

  private async executeWithReporting<T>(options: {
    taskLabel: string
    taskId?: string
    reportConfig?: OutreachFilterConfigInput['report']
    run: () => Promise<T>
    onSuccess?: (
      client: SellerRpaApiClient,
      meta: { startedAt: Date; finishedAt: Date },
      result: T
    ) => Promise<void>
  }): Promise<T> {
    const client = SellerRpaApiClient.create(this.logger, options.reportConfig)
    const startedAt = new Date()

    await this.safeReportTaskStart(client, options.taskId, startedAt, options.taskLabel)
    const heartbeatTimer = this.startHeartbeatLoop(client, options.taskId, options.taskLabel)

    try {
      const result = await options.run()
      const finishedAt = new Date()

      if (client && options.onSuccess) {
        await options.onSuccess(client, { startedAt, finishedAt }, result)
      }

      await this.safeReportTaskComplete(client, options.taskId, finishedAt, options.taskLabel)
      return result
    } catch (error) {
      const finishedAt = new Date()
      await this.safeReportTaskFail(client, options.taskId, finishedAt, error, options.taskLabel)
      throw error
    } finally {
      if (heartbeatTimer) {
        clearInterval(heartbeatTimer)
      }
    }
  }

  private startHeartbeatLoop(
    client: SellerRpaApiClient | null,
    taskId: string | undefined,
    taskLabel: string
  ): ReturnType<typeof setInterval> | null {
    if (!client || !taskId) {
      return null
    }

    return setInterval(() => {
      void this.safeReportTaskHeartbeat(client, taskId, new Date(), taskLabel)
    }, client.heartbeatIntervalMs)
  }

  private async safeReportTaskStart(
    client: SellerRpaApiClient | null,
    taskId: string | undefined,
    startedAt: Date,
    taskLabel: string
  ): Promise<void> {
    if (!client || !taskId) {
      return
    }
    try {
      await client.reportTaskStart(taskId, startedAt.toISOString())
    } catch (error) {
      this.logger.warn(
        `[${taskLabel}] start 上报失败: ${taskId} ${(error as Error)?.message || error}`
      )
    }
  }

  private async safeReportTaskHeartbeat(
    client: SellerRpaApiClient | null,
    taskId: string | undefined,
    heartbeatAt: Date,
    taskLabel: string
  ): Promise<void> {
    if (!client || !taskId) {
      return
    }
    try {
      await client.reportTaskHeartbeat(taskId, heartbeatAt.toISOString())
    } catch (error) {
      this.logger.warn(
        `[${taskLabel}] heartbeat 上报失败: ${taskId} ${(error as Error)?.message || error}`
      )
    }
  }

  private async safeReportTaskComplete(
    client: SellerRpaApiClient | null,
    taskId: string | undefined,
    finishedAt: Date,
    taskLabel: string
  ): Promise<void> {
    if (!client || !taskId) {
      return
    }
    try {
      await client.reportTaskComplete(taskId, finishedAt.toISOString())
    } catch (error) {
      this.logger.warn(
        `[${taskLabel}] complete 上报失败: ${taskId} ${(error as Error)?.message || error}`
      )
    }
  }

  private async safeReportTaskFail(
    client: SellerRpaApiClient | null,
    taskId: string | undefined,
    finishedAt: Date,
    error: unknown,
    taskLabel: string
  ): Promise<void> {
    if (!client || !taskId) {
      return
    }
    const errorMessage = (error as Error)?.message || String(error)
    try {
      await client.reportTaskFail(taskId, finishedAt.toISOString(), errorMessage)
    } catch (failError) {
      this.logger.warn(
        `[${taskLabel}] fail 上报失败: ${taskId} ${(failError as Error)?.message || failError}`
      )
    }
  }

  private requireRuntime(): PlaywrightSimulationRuntime {
    if (!this.runtime) {
      throw new Error('Playwright 会话尚未启动。请先点击“启动RPA模拟”或发送 RPA_EXECUTE_SIMULATION。')
    }
    return this.runtime
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
            text: 'Find creators',
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
        ...buildOutreachFilterSteps(filterConfig)
      ]
    } as BrowserTask

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

  private async runChatbotTask(
    taskRunner: BrowserActionRunner,
    region: string,
    payload?: SellerChatbotPayloadInput
  ): Promise<void> {
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
