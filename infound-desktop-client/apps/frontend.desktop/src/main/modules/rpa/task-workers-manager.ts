import { flushPendingSellerRpaReports } from '@infound/desktop-rpa'
import { AbstractWorkerManager } from './abstract-worker-manager'
import { TaskType } from '../../services/task-service'
import { OutReachWorkerManager } from './workers/out-reach-worker'
import { logger } from '../../utils/logger'
import { AppConfig } from '@common/app-config'
import { CreatorDetailWorkerManager } from './workers/creator-detail-worker'
import { SampleMonitorWorker } from './workers/sample-monitor-worker'
import { UrgeChatWorkerManager } from './workers/urge-chat-worker'
import { ChatWorkerManager } from './workers/chat-worker'
import { taskReportRetryService } from './task-report-retry-service'

export class TaskWorkersManager {
  private static readonly POLLING_INTERVAL_MS = AppConfig.TASK_MANAGER_POLLING_INTERVAL_MS
  private static readonly PENDING_FLUSH_MAX_ITEMS = 10
  private readonly workers: Partial<Record<TaskType, AbstractWorkerManager>> = {}
  private initialized = false
  private pollingTimer: NodeJS.Timeout | null = null
  private pendingFlushPromise: Promise<void> | null = null

  constructor() {
    this.workers[TaskType.Chat] = new ChatWorkerManager()
    this.workers[TaskType.CreatorDetail] = new CreatorDetailWorkerManager()
    this.workers[TaskType.Outreach] = new OutReachWorkerManager()
    this.workers[TaskType.SampleMonitor] = new SampleMonitorWorker()
    this.workers[TaskType.UrgeChat] = new UrgeChatWorkerManager()
  }

  public async init(): Promise<void> {
    if (this.initialized) {
      logger.info('任务管理器已初始化，执行一次补拉唤醒')
      await this.declareIdle()
      return
    }

    this.initialized = true
    this.pollingTimer = setInterval(() => {
      void this.declareIdle()
    }, TaskWorkersManager.POLLING_INTERVAL_MS)

    logger.info(`任务管理器已启动: workers=${Object.keys(this.workers).join(',')} poll=${TaskWorkersManager.POLLING_INTERVAL_MS}ms`)
    await this.declareIdle()
  }

  public async declareIdle(taskType?: TaskType | string): Promise<void> {
    await this.flushPendingReports()
    const targetWorkers = this.resolveTargetWorkers(taskType)
    await Promise.allSettled(targetWorkers.map((worker) => worker.declareIdle()))
  }

  public async cancelTask(
    taskId: string,
    options?: {
      rootTaskId?: string
      cancelScope?: string
    }
  ): Promise<void> {
    await Promise.allSettled(this.getAllWorkers().map((worker) => worker.cancelTask(taskId, options)))
  }

  public async stop(): Promise<void> {
    if (this.pollingTimer) {
      clearInterval(this.pollingTimer)
      this.pollingTimer = null
    }
    this.initialized = false
  }

  private resolveTargetWorkers(taskType?: TaskType | string): AbstractWorkerManager[] {
    if (!taskType) {
      return this.getAllWorkers()
    }

    const normalizedType = String(taskType).trim().toUpperCase() as TaskType
    const worker = this.workers[normalizedType]
    return worker ? [worker] : this.getAllWorkers()
  }

  private getAllWorkers(): AbstractWorkerManager[] {
    return Object.values(this.workers).filter((worker): worker is AbstractWorkerManager => Boolean(worker))
  }

  private async flushPendingReports(): Promise<void> {
    if (this.pendingFlushPromise) {
      await this.pendingFlushPromise
      return
    }

    this.pendingFlushPromise = this.doFlushPendingReports().finally(() => {
      this.pendingFlushPromise = null
    })
    await this.pendingFlushPromise
  }

  private async doFlushPendingReports(): Promise<void> {
    try {
      const taskReportResult = await taskReportRetryService.flushPendingReports(
        TaskWorkersManager.PENDING_FLUSH_MAX_ITEMS
      )
      const sellerReportResult = await flushPendingSellerRpaReports(
        logger,
        TaskWorkersManager.PENDING_FLUSH_MAX_ITEMS
      )

      if (taskReportResult.processed > 0 || sellerReportResult.processed > 0) {
        const summary = `taskReport=${taskReportResult.succeeded}/${taskReportResult.processed} sellerReport=${sellerReportResult.succeeded}/${sellerReportResult.processed}`
        if (taskReportResult.failed > 0 || sellerReportResult.failed > 0) {
          logger.warn(
            `容错补发检查: ${summary} failed=${taskReportResult.failed + sellerReportResult.failed}`
          )
        } else {
          logger.info(`容错补发检查: ${summary}`)
        }
      }
    } catch (error) {
      logger.warn(`待补发队列刷新失败: ${(error as Error)?.message || error}`)
    }
  }
}

export const taskWorkersManager = new TaskWorkersManager()
