import { AbstractWorkerManager } from './abstract-worker-manager'
import { TaskType } from '../../services/task-service'
import { ChatWorkerManager } from './workers/chat-worker'
import { CreatorDetailWorkerManager } from './workers/creator-detail-worker'
import { OutReachWorkerManager } from './workers/out-reach-worker'
import { SampleMonitorWorker } from './workers/sample-monitor-worker'
import { logger } from '../../utils/logger'

export class TaskWorkersManager {
  private readonly workers: Partial<Record<TaskType, AbstractWorkerManager>> = {}
  private initialized = false
  private pollingTimer: NodeJS.Timeout | null = null
  private static readonly POLLING_INTERVAL_MS = 5000

  constructor() {
    this.workers[TaskType.Chat] = new ChatWorkerManager()
    this.workers[TaskType.CreatorDetail] = new CreatorDetailWorkerManager()
    this.workers[TaskType.Outreach] = new OutReachWorkerManager()
    this.workers[TaskType.SampleMonitor] = new SampleMonitorWorker()
  }

  public async init(): Promise<void> {
    if (this.initialized) {
      logger.info('任务管理器已初始化，执行一次补拉唤醒')
      await this.wakeUp()
      return
    }

    this.initialized = true
    this.pollingTimer = setInterval(() => {
      void this.wakeUp()
    }, TaskWorkersManager.POLLING_INTERVAL_MS)

    logger.info(
      `任务管理器已启动: workers=${Object.keys(this.workers).join(',')} poll=${TaskWorkersManager.POLLING_INTERVAL_MS}ms`
    )
    await this.wakeUp()
  }

  public async wakeUp(taskType?: TaskType | string): Promise<void> {
    const targetWorkers = this.resolveTargetWorkers(taskType)
    await Promise.allSettled(targetWorkers.map((worker) => worker.wakeUp()))
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
}

export const taskWorkersManager = new TaskWorkersManager()
