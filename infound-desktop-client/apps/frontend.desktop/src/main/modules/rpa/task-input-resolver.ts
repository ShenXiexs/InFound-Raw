import fs from 'fs'
import path from 'path'
import { app } from 'electron'
import { AppConfig } from '@common/app-config'
import { TK_CONTENTS } from '@common/app-constants'
import type {
  LoginStateCookieInput,
  OutreachFilterConfigInput,
  PlaywrightSimulationPayloadInput,
  SampleManagementPayloadInput,
  SellerChatbotPayloadInput,
  SellerCreatorDetailPayloadInput,
  SellerRpaReportConfigInput
} from '@desktop-rpa'
import { TaskInfo, TaskType } from '../../services/task-service'
import { globalState } from '../state/global-state'
import { logger } from '../../utils/logger'

const DEFAULT_REGION = 'MX'
const DEFAULT_AUTH_HEADER = 'INFoundSellerAuth'

type JsonRecord = Record<string, unknown>

interface ResolvedTaskEnvelope {
  sessionNode: JsonRecord
  payloadNode: JsonRecord
  taskNode: JsonRecord
  reportNode: JsonRecord
}

const isRecord = (value: unknown): value is JsonRecord => value != null && typeof value === 'object' && !Array.isArray(value)

const parseJsonLike = (value: unknown): unknown => {
  if (typeof value !== 'string') {
    return value
  }

  const trimmed = value.trim()
  if (!trimmed) {
    return value
  }

  const looksLikeJson = (trimmed.startsWith('{') && trimmed.endsWith('}')) || (trimmed.startsWith('[') && trimmed.endsWith(']'))
  if (!looksLikeJson) {
    return value
  }

  try {
    return JSON.parse(trimmed) as unknown
  } catch {
    return value
  }
}

const asRecord = (value: unknown): JsonRecord => {
  const parsed = parseJsonLike(value)
  return isRecord(parsed) ? parsed : {}
}

const toText = (value: unknown): string => {
  if (typeof value === 'string') {
    return value.trim()
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value).trim()
  }
  return ''
}

const toBoolean = (value: unknown): boolean | undefined => {
  if (typeof value === 'boolean') {
    return value
  }
  const normalized = toText(value).toLowerCase()
  if (!normalized) {
    return undefined
  }
  if (['1', 'true', 'yes', 'y', 'on'].includes(normalized)) {
    return true
  }
  if (['0', 'false', 'no', 'n', 'off'].includes(normalized)) {
    return false
  }
  return undefined
}

const expandUserDataPath = (inputPath: string): string => {
  if (!/%userData%/i.test(inputPath)) {
    return inputPath
  }

  return inputPath.replace(/%userData%/gi, app.getPath('userData'))
}

const resolveExistingTaskJsonPath = (inputPath: string): string => {
  const trimmedPath = toText(inputPath)
  if (!trimmedPath || trimmedPath.startsWith('{') || trimmedPath.startsWith('[')) {
    return ''
  }

  const normalizedPath = expandUserDataPath(trimmedPath)
  const candidatePaths = path.isAbsolute(normalizedPath)
    ? [normalizedPath]
    : [
        path.resolve(process.cwd(), normalizedPath),
        path.resolve(process.cwd(), '..', normalizedPath),
        path.resolve(process.cwd(), '..', '..', normalizedPath),
        path.resolve(process.cwd(), '..', '..', '..', normalizedPath)
      ]

  return candidatePaths.find((candidatePath) => fs.existsSync(candidatePath)) || ''
}

const resolveTaskShopId = (taskNode: JsonRecord, payloadNode: JsonRecord): string => toText(payloadNode.shopId) || toText(taskNode.shopId)

const resolveLocalExportedLoginStatePath = (taskNode: JsonRecord, payloadNode: JsonRecord): string => {
  const currentUser = globalState.currentState.currentUser
  const userId = toText(currentUser?.userId)
  const shopId = resolveTaskShopId(taskNode, payloadNode)
  if (!userId || !shopId) {
    return ''
  }

  const loginStateFolder = path.join(app.getPath('userData'), TK_CONTENTS.KEY, userId, shopId)
  if (!fs.existsSync(loginStateFolder)) {
    return ''
  }

  const candidates = fs
    .readdirSync(loginStateFolder, { withFileTypes: true })
    .filter((entry) => entry.isFile() && entry.name.endsWith('.json'))
    .map((entry) => {
      const filePath = path.join(loginStateFolder, entry.name)
      return {
        filePath,
        mtimeMs: fs.statSync(filePath).mtimeMs
      }
    })
    .sort((a, b) => b.mtimeMs - a.mtimeMs)

  return candidates[0]?.filePath || ''
}

const resolveEffectiveLoginStatePath = (sessionNode: JsonRecord, taskNode: JsonRecord, payloadNode: JsonRecord): string => {
  const explicitLoginStatePath = toText(sessionNode.loginStatePath)
  if (explicitLoginStatePath) {
    const resolvedExplicitPath = resolveExistingTaskJsonPath(explicitLoginStatePath)
    if (resolvedExplicitPath) {
      return resolvedExplicitPath
    }
    logger.warn(`任务指定的 loginStatePath 不存在，回退本地导出目录继续查找: ${explicitLoginStatePath}`)
  }

  return resolveLocalExportedLoginStatePath(taskNode, payloadNode)
}

const logResolvedLoginStatePath = (session: PlaywrightSimulationPayloadInput): void => {
  const loginStatePath = toText(session.loginStatePath)
  if (loginStatePath) {
    logger.info(`本次实际使用的登录态路径: ${loginStatePath}`)
    return
  }

  logger.warn('本次实际使用的登录态路径: 未找到，将回退为手动登录')
}

const hasEnvelopeShape = (value: JsonRecord): boolean => 'input' in value || 'task' in value || 'executor' in value

const resolveTaskEnvelope = (task: TaskInfo): ResolvedTaskEnvelope => {
  const taskData = asRecord(task.task_data)
  const directQueueName = toText(taskData.queue).toLowerCase()

  if (directQueueName) {
    return {
      sessionNode: asRecord(taskData.session),
      payloadNode: asRecord(taskData.payload),
      taskNode: asRecord(taskData.task),
      reportNode: asRecord(taskData.report)
    }
  }

  const nestedPayload = asRecord(taskData.payload)
  const container = hasEnvelopeShape(taskData) ? taskData : hasEnvelopeShape(nestedPayload) ? nestedPayload : taskData
  const inputNode = asRecord(container.input)
  const payloadNode = asRecord(inputNode.payload)

  return {
    sessionNode: asRecord(inputNode.session),
    payloadNode,
    taskNode: asRecord(container.task),
    reportNode: asRecord(inputNode.report ?? payloadNode.report)
  }
}

const buildDefaultReportConfig = (): SellerRpaReportConfigInput | undefined => {
  const currentUser = globalState.currentState.currentUser
  const baseUrl = toText(AppConfig.OPENAPI_BASE_URL)
  const authToken = toText(currentUser?.tokenValue)
  const deviceId = toText(globalState.currentState.appInfo?.deviceId)
  if (!baseUrl || !authToken) {
    return undefined
  }
  return {
    enabled: true,
    baseUrl,
    authToken,
    authHeader: toText(currentUser?.tokenName) || DEFAULT_AUTH_HEADER,
    deviceId,
    deviceType: 'desktop'
  }
}

const buildReportConfig = (reportNode: JsonRecord): SellerRpaReportConfigInput | undefined => {
  const fallback = buildDefaultReportConfig()
  const explicitEnabled = toBoolean(reportNode.enabled)
  const explicitBaseUrl = toText(reportNode.baseUrl)
  const explicitAuthToken = toText(reportNode.authToken)
  const explicitAuthHeader = toText(reportNode.authHeader)
  const explicitDeviceId = toText(reportNode.deviceId)
  const explicitDeviceType = toText(reportNode.deviceType)

  if (
    explicitEnabled === undefined &&
    !explicitBaseUrl &&
    !explicitAuthToken &&
    !explicitAuthHeader &&
    !explicitDeviceId &&
    !explicitDeviceType
  ) {
    return fallback
  }

  return {
    enabled: explicitEnabled ?? fallback?.enabled ?? true,
    baseUrl: explicitBaseUrl || fallback?.baseUrl,
    authToken: explicitAuthToken || fallback?.authToken,
    authHeader: explicitAuthHeader || fallback?.authHeader || DEFAULT_AUTH_HEADER,
    deviceId: explicitDeviceId || fallback?.deviceId,
    deviceType: explicitDeviceType || fallback?.deviceType
  }
}

const buildSimulationSession = (sessionNode: JsonRecord, taskNode: JsonRecord, payloadNode: JsonRecord): PlaywrightSimulationPayloadInput => {
  const session: PlaywrightSimulationPayloadInput = {
    region: toText(sessionNode.region) || toText(taskNode.shopRegionCode) || toText(payloadNode.shopRegionCode) || DEFAULT_REGION
  }

  const headless = toBoolean(sessionNode.headless)
  if (headless !== undefined) {
    session.headless = headless
  }

  const storageStatePath = toText(sessionNode.storageStatePath)
  if (storageStatePath) {
    session.storageStatePath = storageStatePath
  }

  const loginStatePath = resolveEffectiveLoginStatePath(sessionNode, taskNode, payloadNode)
  if (loginStatePath) {
    session.loginStatePath = loginStatePath
  }

  if (Array.isArray(sessionNode.loginState)) {
    session.loginState = sessionNode.loginState as LoginStateCookieInput[]
  }

  return session
}

const buildTaskContext = (task: TaskInfo, taskNode: JsonRecord, payloadNode: JsonRecord, reportNode: JsonRecord): JsonRecord => {
  const taskId = toText(payloadNode.taskId) || toText(taskNode.taskId) || task.id
  const taskName = toText(payloadNode.taskName) || toText(taskNode.taskName)
  const shopId = toText(payloadNode.shopId) || toText(taskNode.shopId)
  const shopRegionCode = toText(payloadNode.shopRegionCode) || toText(taskNode.shopRegionCode) || DEFAULT_REGION

  const context: JsonRecord = {
    ...payloadNode,
    taskId,
    shopRegionCode,
    executionMode: 'desktop_worker'
  }

  if (taskName) {
    context.taskName = taskName
  }
  if (shopId) {
    context.shopId = shopId
  }

  const report = buildReportConfig(reportNode)
  if (report) {
    context.report = report
  }

  return context
}

export const resolveOutreachTaskInput = (
  task: TaskInfo
): {
  session: PlaywrightSimulationPayloadInput
  payload: OutreachFilterConfigInput
} => {
  const envelope = resolveTaskEnvelope(task)
  const session = buildSimulationSession(envelope.sessionNode, envelope.taskNode, envelope.payloadNode)
  logResolvedLoginStatePath(session)

  return {
    session,
    payload: buildTaskContext(task, envelope.taskNode, envelope.payloadNode, envelope.reportNode) as OutreachFilterConfigInput
  }
}

export const resolveChatTaskInput = (
  task: TaskInfo
): {
  session: PlaywrightSimulationPayloadInput
  payload: SellerChatbotPayloadInput
} => {
  const envelope = resolveTaskEnvelope(task)
  const session = buildSimulationSession(envelope.sessionNode, envelope.taskNode, envelope.payloadNode)
  logResolvedLoginStatePath(session)

  return {
    session,
    payload: buildTaskContext(task, envelope.taskNode, envelope.payloadNode, envelope.reportNode) as SellerChatbotPayloadInput
  }
}

export const resolveUrgeChatTaskInput = (
  task: TaskInfo
): {
  session: PlaywrightSimulationPayloadInput
  payload: SellerChatbotPayloadInput
} => {
  const envelope = resolveTaskEnvelope(task)
  const session = buildSimulationSession(envelope.sessionNode, envelope.taskNode, envelope.payloadNode)
  const payload = buildTaskContext(task, envelope.taskNode, envelope.payloadNode, envelope.reportNode) as SellerChatbotPayloadInput
  payload.businessMode = 'urge'
  payload.taskType = payload.taskType || TaskType.UrgeChat
  logResolvedLoginStatePath(session)

  return {
    session,
    payload
  }
}

export const resolveCreatorDetailTaskInput = (
  task: TaskInfo
): {
  session: PlaywrightSimulationPayloadInput
  payload: SellerCreatorDetailPayloadInput
} => {
  const envelope = resolveTaskEnvelope(task)
  const session = buildSimulationSession(envelope.sessionNode, envelope.taskNode, envelope.payloadNode)
  logResolvedLoginStatePath(session)

  return {
    session,
    payload: buildTaskContext(task, envelope.taskNode, envelope.payloadNode, envelope.reportNode) as SellerCreatorDetailPayloadInput
  }
}

export const resolveSampleTaskInput = (
  task: TaskInfo
): {
  session: PlaywrightSimulationPayloadInput
  payload: SampleManagementPayloadInput
} => {
  const envelope = resolveTaskEnvelope(task)
  const session = buildSimulationSession(envelope.sessionNode, envelope.taskNode, envelope.payloadNode)
  logResolvedLoginStatePath(session)

  return {
    session,
    payload: buildTaskContext(task, envelope.taskNode, envelope.payloadNode, envelope.reportNode) as SampleManagementPayloadInput
  }
}
