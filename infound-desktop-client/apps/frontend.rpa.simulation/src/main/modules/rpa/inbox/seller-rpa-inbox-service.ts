import { createRequire } from 'node:module'
import { resolve } from 'node:path'
import { AppConfig } from '@common/app-config'
import type { SellerChatbotPayloadInput } from '@common/types/rpa-chatbot'
import type { SellerCreatorDetailPayloadInput } from '@common/types/rpa-creator-detail'
import type { OutreachFilterConfigInput } from '@common/types/rpa-outreach'
import type { SampleManagementPayloadInput } from '@common/types/rpa-sample-management'
import type { SellerRpaMqMessage } from '@common/types/seller-rpa-mq'
import type { PlaywrightSimulationPayloadInput } from '@common/types/rpa-simulation'
import type { SellerRpaReportConfigInput } from '@common/types/seller-rpa-report'
import type { RPAController } from '../../ipc/rpa-controller'
import { SellerRpaTaskMqService } from '../mq/seller-rpa-task-mq-service'
import { logger } from '../../../utils/logger'

type TaskType = 'OUTREACH' | 'CHAT' | 'CREATOR_DETAIL' | 'SAMPLE'

interface SellerRpaTaskReadyEnvelope {
  eventType?: unknown
  messageId?: unknown
  userId?: unknown
  taskId?: unknown
  taskType?: unknown
  scheduledTime?: unknown
  expiresAt?: unknown
  payload?: unknown
}

interface SellerRpaEnvelopePayload {
  executor?: Record<string, unknown>
  task?: Record<string, unknown>
  input?: Record<string, unknown>
}

interface StompFrameLike {
  body?: string
}

interface StompMessageLike {
  body: string
  ack: () => void
  nack: () => void
}

interface StompSubscriptionLike {
  unsubscribe: () => void
}

interface StompClientLike {
  active: boolean
  subscribe: (
    destination: string,
    callback: (message: StompMessageLike) => void,
    headers?: Record<string, string>
  ) => StompSubscriptionLike
  activate: () => void
  deactivate: () => Promise<void>
}

type StompClientConstructor = new (config: Record<string, unknown>) => StompClientLike
type WebSocketConstructor = new (url: string, options?: Record<string, unknown>) => unknown

const PROCESSING_CACHE_TTL_MS = 6 * 60 * 60 * 1000
const requireModule = createRequire(import.meta.url)

const asRecord = (value: unknown): Record<string, unknown> =>
  value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {}

const toText = (value: unknown): string => String(value ?? '').trim()

const readScriptCandidate = (
  primary: Record<string, unknown>,
  secondary: Record<string, unknown>,
  ...keys: string[]
): unknown => {
  for (const key of keys) {
    if (key in primary) {
      return primary[key]
    }
    if (key in secondary) {
      return secondary[key]
    }
  }
  return undefined
}

const toBoolean = (value: unknown, defaultValue = false): boolean => {
  if (typeof value === 'boolean') {
    return value
  }
  const normalized = String(value ?? '').trim().toLowerCase()
  if (!normalized) {
    return defaultValue
  }
  if (['1', 'true', 'yes', 'y', 'on'].includes(normalized)) {
    return true
  }
  if (['0', 'false', 'no', 'n', 'off'].includes(normalized)) {
    return false
  }
  return defaultValue
}

const parseJson = (text: string): unknown => {
  try {
    return JSON.parse(text)
  } catch {
    return null
  }
}

export class SellerRpaInboxService {
  private static instance: SellerRpaInboxService | null = null

  public static getInstance(): SellerRpaInboxService {
    if (!SellerRpaInboxService.instance) {
      SellerRpaInboxService.instance = new SellerRpaInboxService()
    }
    return SellerRpaInboxService.instance
  }

  private client: StompClientLike | null = null
  private subscription: StompSubscriptionLike | null = null
  private connected = false
  private rpaController: RPAController | null = null
  private processedMessageIds = new Map<string, number>()

  private constructor() {}

  public async start(rpaController: RPAController): Promise<void> {
    this.rpaController = rpaController
    SellerRpaTaskMqService.getInstance().start(rpaController.getSimulationService())

    if (!AppConfig.SELLER_RPA_WS_ENABLED) {
      logger.info('[seller-rpa-inbox] 收件箱订阅已禁用')
      return
    }

    const wsBaseUrl = AppConfig.SELLER_RPA_WS_BASE_URL
    const authToken = AppConfig.SELLER_RPA_WS_TOKEN
    const userId = AppConfig.SELLER_RPA_WS_USER_ID
    if (!wsBaseUrl || !authToken || !userId) {
      logger.warn(
        '[seller-rpa-inbox] 缺少 WS_BASE_URL / TOKEN / USER_ID，跳过收件箱订阅启动'
      )
      return
    }

    if (this.client?.active) {
      return
    }

    const { StompClient, WebSocketImpl } = this.loadRuntimeDependencies()

    this.client = new StompClient({
      webSocketFactory: () =>
        new WebSocketImpl(wsBaseUrl, {
          headers: {
            [AppConfig.SELLER_RPA_WS_AUTH_HEADER]: authToken
          },
          rejectUnauthorized: AppConfig.IS_PRO
        }),
      heartbeatIncoming: AppConfig.SELLER_RPA_WS_HEARTBEAT_INCOMING_MS,
      heartbeatOutgoing: AppConfig.SELLER_RPA_WS_HEARTBEAT_OUTGOING_MS,
      reconnectDelay: AppConfig.SELLER_RPA_WS_RECONNECT_DELAY_MS,
      onConnect: (frame) => {
        this.connected = true
        this.subscribeInbox(frame)
      },
      onDisconnect: () => {
        this.connected = false
        this.subscription = null
        logger.warn('[seller-rpa-inbox] STOMP 连接已断开')
      },
      onStompError: (frame) => {
        logger.error(`[seller-rpa-inbox] STOMP 错误: ${frame.body || '(empty)'}`)
      },
      onWebSocketError: (event) => {
        logger.error(`[seller-rpa-inbox] WebSocket 错误: ${JSON.stringify(event)}`)
      }
    })

    this.client.activate()
    logger.info('[seller-rpa-inbox] 已启动 seller 收件箱订阅客户端')
  }

  public async stop(): Promise<void> {
    this.subscription?.unsubscribe()
    this.subscription = null
    if (this.client) {
      await this.client.deactivate()
    }
    this.client = null
    this.connected = false
    SellerRpaTaskMqService.getInstance().stop()
  }

  public isConnected(): boolean {
    return this.connected
  }

  public async dispatchEnvelopeForTesting(
    envelope: unknown,
    rpaController: RPAController
  ): Promise<void> {
    this.rpaController = rpaController
    const normalizedEnvelope =
      envelope && typeof envelope === 'object' && !Array.isArray(envelope)
        ? (envelope as SellerRpaTaskReadyEnvelope)
        : null
    if (!normalizedEnvelope) {
      throw new Error('seller inbox 测试消息必须是 JSON object')
    }
    await this.dispatchEnvelope(normalizedEnvelope)
  }

  private subscribeInbox(_frame: StompFrameLike): void {
    if (!this.client || !this.rpaController) {
      return
    }

    this.subscription?.unsubscribe()
    const destination = this.resolveInboxDestination(AppConfig.SELLER_RPA_WS_USER_ID)
    this.subscription = this.client.subscribe(
      destination,
      (message) => {
        void this.handleMessage(message)
      },
      {
        ack: 'client-individual',
        durable: 'true',
        'auto-delete': 'false',
        'prefetch-count': '1'
      }
    )
    logger.info(`[seller-rpa-inbox] 已订阅 seller 收件箱: ${destination}`)
  }

  private resolveInboxDestination(userId: string): string {
    const explicit = AppConfig.SELLER_RPA_WS_INBOX_DESTINATION
    if (explicit) {
      return explicit.includes('{userId}') ? explicit.replaceAll('{userId}', userId) : explicit
    }
    return `/amq/queue/seller.rpa.user.inbox.${userId}`
  }

  private async handleMessage(message: StompMessageLike): Promise<void> {
    const envelope = parseJson(message.body) as SellerRpaTaskReadyEnvelope | null
    if (!envelope || typeof envelope !== 'object') {
      logger.error('[seller-rpa-inbox] 收到无法解析的消息体')
      this.safeAck(message)
      return
    }

    const eventType = toText(envelope.eventType)
    if (eventType !== 'RPA_TASK_READY') {
      logger.warn(`[seller-rpa-inbox] 忽略非 RPA_TASK_READY 消息: ${eventType || '(empty)'}`)
      this.safeAck(message)
      return
    }

    const messageId = toText(envelope.messageId)
    if (messageId && this.isRecentlyProcessed(messageId)) {
      logger.warn(`[seller-rpa-inbox] 忽略重复消息: ${messageId}`)
      this.safeAck(message)
      return
    }

    const expiresAt = toText(envelope.expiresAt)
    if (expiresAt) {
      const expiresMs = Date.parse(expiresAt)
      if (Number.isFinite(expiresMs) && expiresMs <= Date.now()) {
        logger.warn(`[seller-rpa-inbox] 忽略已过期消息: ${messageId || '(no-message-id)'}`)
        this.safeAck(message)
        return
      }
    }

    try {
      await this.dispatchEnvelope(envelope)
      if (messageId) {
        this.processedMessageIds.set(messageId, Date.now())
      }
      this.compactProcessedMessageIds()
      this.safeAck(message)
    } catch (error) {
      logger.error(
        `[seller-rpa-inbox] 任务分发失败: ${(error as Error)?.message || error}`
      )
      this.safeNack(message)
    }
  }

  private async dispatchEnvelope(envelope: SellerRpaTaskReadyEnvelope): Promise<void> {
    if (!this.rpaController) {
      throw new Error('RPAController not initialized')
    }

    const normalizedTaskType = toText(envelope.taskType).toUpperCase() as TaskType | ''
    const envelopePayload = asRecord(envelope.payload) as SellerRpaEnvelopePayload
    const executor = asRecord(envelopePayload.executor)
    const task = asRecord(envelopePayload.task)
    const input = asRecord(envelopePayload.input)
    const inputPayload = asRecord(input.payload)

    const host = toText(executor.host)
    if (host && host !== 'frontend.rpa.simulation') {
      logger.warn(`[seller-rpa-inbox] 忽略发往其他宿主的任务: host=${host}`)
      return
    }

    const message = this.buildMqMessage(envelope, normalizedTaskType, task, input, inputPayload)
    if (!message) {
      const dispatchCommand = this.resolveDispatchCommand(executor, normalizedTaskType)
      logger.warn(
        `[seller-rpa-inbox] 暂不支持的任务类型: taskType=${normalizedTaskType} dispatchCommand=${dispatchCommand}`
      )
      return
    }

    await this.dispatchMqMessage(message)
  }

  private resolveDispatchCommand(
    executor: Record<string, unknown>,
    taskType: TaskType | ''
  ): string {
    const explicit = toText(executor.dispatchCommand)
    if (explicit) {
      return explicit
    }
    if (taskType === 'OUTREACH') {
      return 'RPA_SELLER_OUT_REACH'
    }
    if (taskType === 'CHAT') {
      return 'RPA_SELLER_CHATBOT'
    }
    if (taskType === 'CREATOR_DETAIL') {
      return 'RPA_SELLER_CREATOR_DETAIL'
    }
    if (taskType === 'SAMPLE') {
      return 'RPA_SAMPLE_MANAGEMENT'
    }
    return ''
  }

  private buildSessionPayload(
    task: Record<string, unknown>,
    input: Record<string, unknown>
  ): PlaywrightSimulationPayloadInput {
    const session = asRecord(input.session)
    const region =
      toText(session.region) || toText(task.shopRegionCode) || toText(task.region) || 'MX'
    const payload: PlaywrightSimulationPayloadInput = {
      region
    }

    const headless = session.headless
    if (headless !== undefined) {
      payload.headless = toBoolean(headless, false)
    }

    const storageStatePath = toText(session.storageStatePath)
    if (storageStatePath) {
      payload.storageStatePath = storageStatePath
    }

    const loginStatePath = toText(session.loginStatePath)
    if (loginStatePath) {
      payload.loginStatePath = loginStatePath
    }

    if (Array.isArray(session.loginState)) {
      payload.loginState = session.loginState as PlaywrightSimulationPayloadInput['loginState']
    }

    return payload
  }

  private buildOutreachPayload(
    envelope: SellerRpaTaskReadyEnvelope,
    task: Record<string, unknown>,
    inputPayload: Record<string, unknown>
  ): OutreachFilterConfigInput {
    const input = asRecord((asRecord(envelope.payload) as SellerRpaEnvelopePayload | null)?.input)
    const rawFilterScript =
      readScriptCandidate(input, inputPayload, 'filterScript', 'script')
    const rawFilterScriptPath =
      toText(readScriptCandidate(input, inputPayload, 'filterScriptPath', 'scriptPath')) || undefined

    const payload: OutreachFilterConfigInput = {
      ...inputPayload,
      taskId: toText(task.taskId) || toText(envelope.taskId) || undefined,
      shopId: toText(task.shopId) || toText(inputPayload.shopId) || undefined,
      taskName: toText(task.taskName) || toText(inputPayload.taskName) || undefined,
      shopRegionCode:
        toText(task.shopRegionCode) || toText(inputPayload.shopRegionCode) || undefined,
      scheduledTime:
        toText(task.scheduledTime) || toText(envelope.scheduledTime) || undefined,
      report: this.buildDefaultReportConfig()
    }
    if (typeof rawFilterScript === 'string' && !rawFilterScriptPath) {
      payload.filterScriptPath = rawFilterScript
    } else if (rawFilterScript && typeof rawFilterScript === 'object' && !Array.isArray(rawFilterScript)) {
      payload.filterScript = rawFilterScript as Record<string, unknown>
    }
    if (rawFilterScriptPath) {
      payload.filterScriptPath = rawFilterScriptPath
    }
    return payload
  }

  private buildChatbotPayload(
    envelope: SellerRpaTaskReadyEnvelope,
    task: Record<string, unknown>,
    inputPayload: Record<string, unknown>
  ): SellerChatbotPayloadInput {
    return {
      ...inputPayload,
      taskId: toText(task.taskId) || toText(envelope.taskId) || undefined,
      shopId: toText(task.shopId) || toText(inputPayload.shopId) || undefined,
      taskName: toText(task.taskName) || toText(inputPayload.taskName) || undefined,
      shopRegionCode:
        toText(task.shopRegionCode) || toText(inputPayload.shopRegionCode) || undefined,
      scheduledTime:
        toText(task.scheduledTime) || toText(envelope.scheduledTime) || undefined,
      creatorId: toText(inputPayload.creatorId) || toText(inputPayload.creator_id) || undefined,
      message: toText(inputPayload.message) || undefined
    }
  }

  private buildCreatorDetailPayload(
    envelope: SellerRpaTaskReadyEnvelope,
    task: Record<string, unknown>,
    inputPayload: Record<string, unknown>
  ): SellerCreatorDetailPayloadInput {
    return {
      ...inputPayload,
      taskId: toText(task.taskId) || toText(envelope.taskId) || undefined,
      shopId: toText(task.shopId) || toText(inputPayload.shopId) || undefined,
      taskName: toText(task.taskName) || toText(inputPayload.taskName) || undefined,
      shopRegionCode:
        toText(task.shopRegionCode) || toText(inputPayload.shopRegionCode) || undefined,
      scheduledTime:
        toText(task.scheduledTime) || toText(envelope.scheduledTime) || undefined,
      creatorId: toText(inputPayload.creatorId) || toText(inputPayload.creator_id) || undefined
    }
  }

  private buildSamplePayload(
    envelope: SellerRpaTaskReadyEnvelope,
    task: Record<string, unknown>,
    inputPayload: Record<string, unknown>
  ): SampleManagementPayloadInput {
    return {
      ...inputPayload,
      taskId: toText(task.taskId) || toText(envelope.taskId) || undefined,
      shopId: toText(task.shopId) || toText(inputPayload.shopId) || undefined,
      taskName: toText(task.taskName) || toText(inputPayload.taskName) || undefined,
      shopRegionCode:
        toText(task.shopRegionCode) || toText(inputPayload.shopRegionCode) || undefined,
      scheduledTime:
        toText(task.scheduledTime) || toText(envelope.scheduledTime) || undefined
    }
  }

  private buildMqMessage(
    envelope: SellerRpaTaskReadyEnvelope,
    taskType: TaskType | '',
    task: Record<string, unknown>,
    input: Record<string, unknown>,
    inputPayload: Record<string, unknown>
  ): SellerRpaMqMessage | null {
    const session = this.buildSessionPayload(task, input)
    const metadata = {
      messageId: toText(envelope.messageId) || undefined,
      source: 'seller_inbox'
    }
    if (taskType === 'OUTREACH') {
      return {
        queue: 'outreach',
        session,
        metadata,
        payload: this.buildOutreachPayload(envelope, task, inputPayload)
      }
    }
    if (taskType === 'CHAT') {
      return {
        queue: 'chat',
        session,
        metadata,
        payload: this.buildChatbotPayload(envelope, task, inputPayload)
      }
    }
    if (taskType === 'CREATOR_DETAIL') {
      return {
        queue: 'creator_detail',
        session,
        metadata,
        payload: this.buildCreatorDetailPayload(envelope, task, inputPayload)
      }
    }
    if (taskType === 'SAMPLE') {
      return {
        queue: 'sample',
        session,
        metadata,
        payload: this.buildSamplePayload(envelope, task, inputPayload)
      }
    }
    return null
  }

  private async dispatchMqMessage(message: SellerRpaMqMessage): Promise<void> {
    const mqService = SellerRpaTaskMqService.getInstance()
    switch (message.queue) {
      case 'outreach':
        await mqService.publishOutreach(message)
        return
      case 'chat':
        await mqService.publishChat(message)
        return
      case 'creator_detail':
        await mqService.publishCreatorDetail(message)
        return
      case 'sample':
        await mqService.publishSample(message)
        return
      default:
        throw new Error(`unsupported seller mq message queue: ${(message as SellerRpaMqMessage).queue}`)
    }
  }

  private buildDefaultReportConfig(): SellerRpaReportConfigInput | undefined {
    const baseUrl = AppConfig.SELLER_RPA_API_BASE_URL
    const authToken = AppConfig.SELLER_RPA_API_TOKEN || AppConfig.SELLER_RPA_WS_TOKEN
    if (!baseUrl || !authToken) {
      return undefined
    }
    return {
      enabled: true,
      baseUrl,
      authToken,
      authHeader: AppConfig.SELLER_RPA_API_AUTH_HEADER || AppConfig.SELLER_RPA_WS_AUTH_HEADER
    }
  }

  private isRecentlyProcessed(messageId: string): boolean {
    const processedAt = this.processedMessageIds.get(messageId)
    return processedAt !== undefined && Date.now() - processedAt <= PROCESSING_CACHE_TTL_MS
  }

  private compactProcessedMessageIds(): void {
    const now = Date.now()
    for (const [messageId, processedAt] of this.processedMessageIds.entries()) {
      if (now - processedAt > PROCESSING_CACHE_TTL_MS) {
        this.processedMessageIds.delete(messageId)
      }
    }
  }

  private safeAck(message: StompMessageLike): void {
    try {
      message.ack()
    } catch (error) {
      logger.warn(`[seller-rpa-inbox] ack 失败: ${(error as Error)?.message || error}`)
    }
  }

  private safeNack(message: StompMessageLike): void {
    try {
      message.nack()
    } catch (error) {
      logger.warn(`[seller-rpa-inbox] nack 失败: ${(error as Error)?.message || error}`)
    }
  }

  private loadRuntimeDependencies(): {
    StompClient: StompClientConstructor
    WebSocketImpl: WebSocketConstructor
  } {
    const stompModule = requireModule(this.resolveWorkspaceModule('@stomp/stompjs')) as {
      Client?: StompClientConstructor
    }
    const wsModule = requireModule(this.resolveWorkspaceModule('ws')) as {
      default?: WebSocketConstructor
    } & WebSocketConstructor

    const StompClient = stompModule.Client
    const WebSocketImpl =
      wsModule.default || (wsModule as unknown as WebSocketConstructor)

    if (!StompClient || !WebSocketImpl) {
      throw new Error('无法加载 seller inbox 所需的 STOMP / WebSocket 运行时依赖')
    }

    return { StompClient, WebSocketImpl }
  }

  private resolveWorkspaceModule(moduleId: string): string {
    const searchBases = [
      process.cwd(),
      resolve(process.cwd(), '..', 'frontend.desktop'),
      resolve(process.cwd(), '..', '..'),
      resolve(process.cwd(), '..', '..', 'node_modules', '.pnpm', 'node_modules')
    ]

    for (const base of searchBases) {
      try {
        return requireModule.resolve(moduleId, { paths: [base] })
      } catch {
        continue
      }
    }

    throw new Error(`无法在当前 workspace 中解析依赖: ${moduleId}`)
  }
}
