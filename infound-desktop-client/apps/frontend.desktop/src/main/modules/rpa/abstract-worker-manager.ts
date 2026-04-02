import { claimTaskAsync, heartbeatAsync, reportAsync, TaskInfo, TaskStatus, TaskType } from '../../services/task-service'
import { logger } from '../../utils/logger'
import { WorkerStatus } from './task-type'

export abstract class AbstractWorkerManager {
  protected status: WorkerStatus = WorkerStatus.IDLE
  private currentTask: TaskInfo | undefined
  private currentCancelled = false
  private currentCancelReason: string | undefined

  // 抽象属性：子类必须提供其对应的任务类型
  protected abstract get taskType(): TaskType

  public isIdle(): boolean {
    return this.status === WorkerStatus.IDLE
  }

  public async wakeUp(): Promise<void> {
    await this.requestNextTask()
  }

  // 1. 宣告空闲并拉取
  public async declareIdle(): Promise<void> {
    if (this.status === WorkerStatus.EXECUTING) {
      return
    }
    this.status = WorkerStatus.IDLE
    await this.requestNextTask()
  }

  public async cancelTask(
    taskId: string,
    options?: {
      rootTaskId?: string
      cancelScope?: string
    }
  ): Promise<void> {
    const normalizedTaskId = this.normalizeText(taskId)
    const normalizedRootTaskId = this.normalizeText(options?.rootTaskId)
    const normalizedCancelScope = this.normalizeText(options?.cancelScope).toUpperCase()
    if (!normalizedTaskId && !normalizedRootTaskId) {
      return
    }

    if (this.currentTask && !this.currentCancelled && this.matchesCancellation(this.currentTask, normalizedTaskId, normalizedRootTaskId, normalizedCancelScope)) {
      this.currentCancelled = true
      this.currentCancelReason = normalizedTaskId || normalizedRootTaskId || `cancel_scope=${normalizedCancelScope || 'TASK'}`

      try {
        await this.abortCurrentTask()
      } catch (error) {
        logger.error(`中断运行中任务失败: type=${this.taskType} taskId=${this.currentTask.id} error=${(error as Error)?.message || error}`)
      }
    }
  }

  // 子类必须实现具体的任务执行逻辑
  protected abstract run(task: TaskInfo): Promise<void>

  protected async abortCurrentTask(): Promise<void> {
    // 子类按需覆盖，默认不执行额外中断逻辑
  }

  protected async requestNextTask(): Promise<void> {
    if (!this.isIdle()) {
      return
    }

    this.status = WorkerStatus.REQUESTING

    try {
      const result = await claimTaskAsync(this.taskType)
      if (result.code !== 200) {
        logger.warn(`CLAIM 返回非成功状态(类型: ${this.taskType}): code=${result.code} msg=${result.msg || ''}`)
        return
      }

      if (!result.data) {
        logger.info(`没有可 CLAIM 的任务(类型: ${this.taskType})`)
        return
      }

      logger.info(`任务已 CLAIM 成功, 开始执行任务(类型: ${this.taskType}): ${result.data.id}`)
      await this.runEngine(result.data)
    } catch (error) {
      logger.error(`CLAIM 任务失败(类型: ${this.taskType}): ${(error as Error)?.message || error}`)
    } finally {
      if (this.status === WorkerStatus.REQUESTING) {
        this.status = WorkerStatus.IDLE
      }
    }
  }

  // 2. 执行引擎
  protected async runEngine(task: TaskInfo): Promise<void> {
    this.status = WorkerStatus.EXECUTING
    this.currentTask = task
    this.currentCancelled = false
    this.currentCancelReason = undefined
    let taskError: Error | undefined

    // 开启心跳上报定时器 (每30秒)
    const heartbeatTimer = this.currentCancelled
      ? null
      : setInterval(() => {
          void this.sendHeartbeat(task.id)
        }, 30000)

    try {
      if (!taskError && !this.currentCancelled) {
        await this.run(task)
      }
    } catch (e) {
      taskError = e as Error
      if (this.currentCancelled) {
        logger.warn(`任务已中断取消：${task.id} reason=${taskError.message}`)
      } else {
        logger.error(`任务执行失败：${taskError.message}`)
      }
    } finally {
      if (heartbeatTimer) {
        clearInterval(heartbeatTimer)
      }
      await this.finalizeTaskExecution(task, taskError)
    }
  }

  private async sendHeartbeat(taskId: string): Promise<void> {
    try {
      await heartbeatAsync(taskId)
    } catch (error) {
      logger.warn(`任务心跳上报失败: taskId=${taskId} error=${(error as Error)?.message || error}`)
    }
  }

  private async sendReport(taskId: string, taskStatus: TaskStatus, error?: string): Promise<void> {
    try {
      await reportAsync(taskId, taskStatus, error)
    } catch (reportError) {
      logger.error(`任务状态上报失败: taskId=${taskId} status=${taskStatus} error=${(reportError as Error)?.message || reportError}`)
    }
  }

  private async finalizeTaskExecution(task: TaskInfo, taskError?: Error): Promise<void> {
    try {
      if (this.currentCancelled) {
        logger.warn(`任务已取消：${task.id}`)
        await this.sendReport(task.id, TaskStatus.Cancelled, this.currentCancelReason || taskError?.message)
      } else if (taskError) {
        await this.sendReport(task.id, TaskStatus.Failed, taskError.message)
      } else {
        logger.info(`任务执行完成：${task.id}`)
        await this.sendReport(task.id, TaskStatus.Completed)
      }
    } finally {
      this.currentTask = undefined
      this.currentCancelled = false
      this.currentCancelReason = undefined
      this.status = WorkerStatus.IDLE
      await this.requestNextTask()
    }
  }

  private matchesCancellation(task: TaskInfo, taskId: string, rootTaskId: string, cancelScope: string): boolean {
    const currentTaskId = this.normalizeText(task.id)
    const currentRootTaskId = this.extractRootTaskId(task)

    if (taskId && currentTaskId === taskId) {
      return true
    }
    if (rootTaskId && currentRootTaskId && currentRootTaskId === rootTaskId) {
      return true
    }
    if (cancelScope && ['ROOT', 'CHAIN', 'CASCADE', 'ALL'].includes(cancelScope) && taskId && currentRootTaskId && currentRootTaskId === taskId) {
      return true
    }
    return false
  }

  private extractRootTaskId(task: TaskInfo): string {
    const taskData = this.asRecord(task.task_data)
    const payload = this.asRecord(taskData.payload)
    const payloadTask = this.asRecord(payload.task)
    const input = this.asRecord(payload.input)
    const inputPayload = this.asRecord(input.payload)
    return this.normalizeText(payloadTask.rootTaskId) || this.normalizeText(inputPayload.rootTaskId) || this.normalizeText(taskData.rootTaskId) || ''
  }

  private asRecord(value: unknown): Record<string, unknown> {
    if (typeof value === 'string') {
      const trimmed = value.trim()
      if (trimmed && ((trimmed.startsWith('{') && trimmed.endsWith('}')) || (trimmed.startsWith('[') && trimmed.endsWith(']')))) {
        try {
          const parsed = JSON.parse(trimmed) as unknown
          return parsed && typeof parsed === 'object' && !Array.isArray(parsed) ? (parsed as Record<string, unknown>) : {}
        } catch {
          return {}
        }
      }
      return {}
    }
    return value && typeof value === 'object' && !Array.isArray(value) ? (value as Record<string, unknown>) : {}
  }

  private normalizeText(value: unknown): string {
    if (typeof value === 'string') {
      return value.trim()
    }
    if (typeof value === 'number' || typeof value === 'boolean') {
      return String(value).trim()
    }
    return ''
  }
}
