import {
  flushPendingPostQueue,
  PendingPostRequestConfig,
  postWithRetryAndQueue
} from '@infound/desktop-rpa'
import { AppConfig } from '@common/app-config'
import { HTTP_HEADERS } from '@common/app-constants'
import { TaskStatus } from '../../services/task-service'
import { API_ENDPOINTS } from '../../services/endpoints'
import { globalState } from '../state/global-state'
import { logger } from '../../utils/logger'

const TASK_REPORT_TIMEOUT_MS = 10000
const TASK_REPORT_RETRY_DELAYS_MS = [0, 1000, 3000, 5000] as const
const TASK_REPORT_PENDING_QUEUE_SCOPE = 'rpa-task-report-pending'

const buildTaskReportPath = (taskId: string): string =>
  API_ENDPOINTS.task.report.replace('{taskId}', encodeURIComponent(String(taskId || '').trim()))

const isByteString = (value: string): boolean =>
  Array.from(String(value || '')).every((char) => char.charCodeAt(0) <= 0xff)

const buildRequestConfig = (taskId: string): PendingPostRequestConfig => {
  const appInfo = globalState.currentState?.appInfo
  const currentUser = globalState.currentState?.currentUser
  const tokenName = String(currentUser?.tokenName || '').trim()
  const tokenValue = String(currentUser?.tokenValue || '').trim()
  if (!tokenName || !tokenValue) {
    throw new Error(`Task report auth token missing: taskId=${taskId}`)
  }

  const headers: Record<string, string> = {
    [HTTP_HEADERS.APP_TYPE]: 'desktop',
    [HTTP_HEADERS.DEVICE_TYPE]: 'desktop',
    [tokenName]: tokenValue
  }

  if (appInfo?.deviceId && isByteString(String(appInfo.deviceId))) {
    headers[HTTP_HEADERS.DEVICE_ID] = String(appInfo.deviceId)
  }
  if (appInfo?.name && isByteString(String(appInfo.name))) {
    headers[HTTP_HEADERS.APP_KEY] = String(appInfo.name)
  }
  if (appInfo?.version && isByteString(String(appInfo.version))) {
    headers[HTTP_HEADERS.APP_VERSION] = String(appInfo.version)
  }

  return {
    baseUrl: AppConfig.OPENAPI_BASE_URL,
    path: buildTaskReportPath(taskId),
    timeoutMs: TASK_REPORT_TIMEOUT_MS,
    responseMode: 'api-code-200',
    headers
  }
}

let flushPromise: Promise<{
  processed: number
  succeeded: number
  failed: number
}> | null = null

const reportTaskStatus = async (
  taskId: string,
  taskStatus: TaskStatus,
  error?: string
): Promise<void> => {
  const normalizedTaskId = String(taskId || '').trim()
  if (!normalizedTaskId) {
    throw new Error('Task report failed: taskId is required')
  }

  const result = await postWithRetryAndQueue({
    scope: TASK_REPORT_PENDING_QUEUE_SCOPE,
    key: normalizedTaskId,
    request: buildRequestConfig(normalizedTaskId),
    payload: {
      task_status: taskStatus,
      error
    },
    logger,
    retryDelaysMs: TASK_REPORT_RETRY_DELAYS_MS,
    label: `task report ${normalizedTaskId}`
  })

  if (result.outcome === 'failed') {
    throw result.error || new Error(`Task report failed: taskId=${normalizedTaskId}`)
  }
  if (result.outcome === 'queued') {
    logger.warn(
      `任务状态上报已进入待补发队列: taskId=${normalizedTaskId} status=${taskStatus} file=${result.queuedFilePath || '(unknown)'}`
    )
  }
}

const flushPendingReports = async (maxItems = 10): Promise<{
  processed: number
  succeeded: number
  failed: number
}> => {
  if (flushPromise) {
    return await flushPromise
  }

  flushPromise = flushPendingPostQueue(TASK_REPORT_PENDING_QUEUE_SCOPE, logger, {
    maxItems,
    label: 'task report'
  }).finally(() => {
    flushPromise = null
  })

  return await flushPromise
}

export const taskReportRetryService = {
  reportTaskStatus,
  flushPendingReports
}
