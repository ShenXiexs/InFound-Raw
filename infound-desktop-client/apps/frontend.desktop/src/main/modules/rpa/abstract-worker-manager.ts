import { claimTaskAsync, heartbeatAsync, TaskInfo, TaskStatus, TaskType } from '../../services/task-service'
import { logger } from '../../utils/logger'
import { WorkerStatus } from './task-type'
import { taskReportRetryService } from './task-report-retry-service'

export abstract class AbstractWorkerManager {
  private static readonly HEARTBEAT_INTERVAL_MS = 30000
  protected status: WorkerStatus = WorkerStatus.IDLE
  private currentTask: TaskInfo | undefined
  private currentCancelled = false
  private currentAbortRequested = false
  private currentCancelReason: string | undefined

  protected abstract get taskType(): TaskType

  protected get taskTimeoutMs(): number | null {
    return null
  }

  protected get faultMonitorReminderIntervalMs(): number | null {
    const timeoutMs = this.getTaskTimeoutMs()
    if (!timeoutMs) {
      return null
    }
    return timeoutMs <= 10 * 60 * 1000 ? 5 * 60 * 1000 : 10 * 60 * 1000
  }

  public isIdle(): boolean {
    return this.status === WorkerStatus.IDLE
  }

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
      this.currentAbortRequested = true
      this.currentCancelReason = normalizedTaskId || normalizedRootTaskId || `cancel_scope=${normalizedCancelScope || 'TASK'}`

      try {
        await this.abortCurrentTask()
      } catch (error) {
        logger.error(`中断运行中任务失败: type=${this.taskType} taskId=${this.currentTask.id} error=${(error as Error)?.message || error}`)
      }
    }
  }

  protected abstract run(task: TaskInfo): Promise<void>

  protected async abortCurrentTask(): Promise<void> {
    // 子类按需覆盖
  }

  protected isCancellationRequested(): boolean {
    return this.currentCancelled || this.currentAbortRequested
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
        logger.debug(`没有可 CLAIM 的任务(类型: ${this.taskType})`)
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

  protected async runEngine(task: TaskInfo): Promise<void> {
    this.status = WorkerStatus.EXECUTING
    this.currentTask = task
    this.currentCancelled = false
    this.currentAbortRequested = false
    this.currentCancelReason = undefined
    let taskError: Error | undefined
    const startedAt = Date.now()
    const timeoutMs = this.getTaskTimeoutMs()

    if (timeoutMs > 0) {
      logger.info(
        `容错监控已启用: type=${this.taskType} taskId=${task.id} timeout=${this.formatDuration(timeoutMs)}`
      )
    }

    const heartbeatTimer = setInterval(() => {
      void this.sendHeartbeat(task.id)
    }, AbstractWorkerManager.HEARTBEAT_INTERVAL_MS)
    const reminderIntervalMs = Math.max(Number(this.faultMonitorReminderIntervalMs || 0) || 0, 0)
    const faultMonitorTimer =
      timeoutMs > 0 && reminderIntervalMs > 0
        ? setInterval(() => {
            logger.info(
              `容错监控中: type=${this.taskType} taskId=${task.id} elapsed=${this.formatDuration(
                Date.now() - startedAt
              )} timeout=${this.formatDuration(timeoutMs)}`
            )
          }, reminderIntervalMs)
        : null
    faultMonitorTimer?.unref?.()

    try {
      if (!this.currentCancelled) {
        await this.executeTaskWithWatchdog(task)
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
      if (faultMonitorTimer) {
        clearInterval(faultMonitorTimer)
      }
      await this.finalizeTaskExecution(task, taskError)
    }
  }

  private async sendHeartbeat(taskId: string): Promise<void> {
    try {
      logger.debug(`发送任务心跳：${taskId}`)
      await heartbeatAsync(taskId)
    } catch (error) {
      logger.warn(`任务心跳上报失败: taskId=${taskId} error=${(error as Error)?.message || error}`)
    }
  }

  private async sendReport(taskId: string, taskStatus: TaskStatus, error?: string): Promise<void> {
    try {
      logger.debug(`发送任务状态：${taskId} status=${taskStatus}`)
      await taskReportRetryService.reportTaskStatus(taskId, taskStatus, error)
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
      this.resetCurrentExecutionState()
      this.status = WorkerStatus.IDLE
      await this.requestNextTask()
    }
  }

  private async executeTaskWithWatchdog(task: TaskInfo): Promise<void> {
    const timeoutMs = this.getTaskTimeoutMs()
    if (!timeoutMs) {
      await this.run(task)
      return
    }

    let timeoutId: NodeJS.Timeout | null = null
    let timedOut = false
    const taskPromise = this.run(task).catch((error) => {
      if (timedOut) {
        logger.warn(`任务超时后的后台执行已结束: type=${this.taskType} taskId=${task.id}`)
        return
      }
      throw error
    })

    const timeoutPromise = new Promise<never>((_, reject) => {
      timeoutId = setTimeout(() => {
        timedOut = true
        this.currentAbortRequested = true
        reject(new Error(`${this.taskType} task execution timeout after ${timeoutMs}ms`))
      }, timeoutMs)
      timeoutId.unref?.()
    })

    try {
      await Promise.race([taskPromise, timeoutPromise])
    } catch (error) {
      if (timedOut) {
        logger.error(`任务执行超时: type=${this.taskType} taskId=${task.id} timeoutMs=${timeoutMs}`)
        try {
          await this.abortCurrentTask()
        } catch (abortError) {
          logger.error(
            `任务超时后中断失败: type=${this.taskType} taskId=${task.id} error=${(abortError as Error)?.message || abortError}`
          )
        }
      }
      throw error
    } finally {
      if (timeoutId) {
        clearTimeout(timeoutId)
      }
    }
  }

  private getTaskTimeoutMs(): number {
    return Math.max(Number(this.taskTimeoutMs || 0) || 0, 0)
  }

  private resetCurrentExecutionState(): void {
    this.currentTask = undefined
    this.currentCancelled = false
    this.currentAbortRequested = false
    this.currentCancelReason = undefined
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

  private formatDuration(durationMs: number): string {
    const totalSeconds = Math.max(Math.floor(durationMs / 1000), 0)
    const hours = Math.floor(totalSeconds / 3600)
    const minutes = Math.floor((totalSeconds % 3600) / 60)

    if (hours > 0) {
      return `${hours}h${minutes > 0 ? `${minutes}m` : ''}`
    }
    return `${Math.max(minutes, 1)}m`
  }
}
