import { claimTaskAsync, heartbeatAsync, reportAsync, TaskInfo, TaskStatus, TaskType } from '../../services/task-service'
import { logger } from '../../utils/logger'
import { WorkerStatus } from './task-type'

export abstract class AbstractWorkerManager {
  protected status: WorkerStatus = WorkerStatus.IDLE
  private readonly pendingTasks: TaskInfo[] = []

  // 抽象属性：子类必须提供其对应的任务类型
  protected abstract get taskType(): TaskType

  public isIdle(): boolean {
    return this.status === WorkerStatus.IDLE
  }

  public async wakeUp(): Promise<void> {
    await this.consumeNextTaskOrClaim()
  }

  public async enqueueTask(task: TaskInfo): Promise<void> {
    this.pendingTasks.push(task)
    await this.consumeNextTaskOrClaim()
  }

  // 1. 宣告空闲并拉取
  public async declareIdle(): Promise<void> {
    if (this.status === WorkerStatus.EXECUTING) {
      return
    }
    this.status = WorkerStatus.IDLE
    await this.consumeNextTaskOrClaim()
  }

  // 子类必须实现具体的任务执行逻辑
  protected abstract run(task: TaskInfo): Promise<void>

  protected async requestNextTask(): Promise<void> {
    if (!this.isIdle() || this.pendingTasks.length > 0) {
      return
    }

    this.status = WorkerStatus.REQUESTING

    try {
      const result = await claimTaskAsync(this.taskType)
      if (result.code !== 200) {
        logger.warn(
          `CLAIM 返回非成功状态(类型: ${this.taskType}): code=${result.code} msg=${result.msg || ''}`
        )
        return
      }

      if (!result.data) {
        logger.info(`没有可 CLAIM 的任务(类型: ${this.taskType})`)
        return
      }

      result.data.task_source = 'claim'
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
    let taskError: Error | undefined
    let shouldExecute = true

    try {
      shouldExecute = await this.prepareTaskForExecution(task)
      if (!shouldExecute) {
        logger.warn(`任务未通过执行前校验，跳过: taskId=${task.id} type=${this.taskType}`)
      }
    } catch (error) {
      taskError = error as Error
      logger.error(`任务执行准备失败：${taskError.message}`)
    }

    if (!shouldExecute) {
      this.status = WorkerStatus.IDLE
      await this.consumeNextTaskOrClaim()
      return
    }

    // 开启心跳上报定时器 (每30秒)
    const heartbeatTimer = setInterval(() => {
      void this.sendHeartbeat(task.id)
    }, 30000)

    try {
      if (!taskError) {
        await this.run(task)
      }
    } catch (e) {
      taskError = e as Error
      logger.error(`任务执行失败：${taskError.message}`)
    } finally {
      clearInterval(heartbeatTimer)

      if (taskError) {
        await this.sendReport(task.id, TaskStatus.Failed, taskError.message)
      } else {
        logger.info(`任务执行完成：${task.id}`)
        await this.sendReport(task.id, TaskStatus.Completed)
      }

      this.status = WorkerStatus.IDLE
      await this.consumeNextTaskOrClaim() // 闭环：优先消费收件箱积压，再补拉 claim
    }
  }

  private async prepareTaskForExecution(task: TaskInfo): Promise<boolean> {
    if (task.task_source !== 'inbox') {
      return true
    }

    const result = await claimTaskAsync(this.taskType, task.id)
    if (result.code !== 200) {
      logger.warn(
        `收件箱任务 CLAIM 失败(类型: ${this.taskType}): taskId=${task.id} code=${result.code} msg=${result.msg || ''}`
      )
      return false
    }

    if (!result.data) {
      logger.warn(`收件箱任务已不可执行，跳过: taskId=${task.id} type=${this.taskType}`)
      return false
    }

    task.task_status = result.data.task_status as TaskStatus
    task.updated_at = result.data.updated_at
    if (
      task.task_data &&
      result.data.task_data &&
      typeof task.task_data === 'object' &&
      !Array.isArray(task.task_data) &&
      typeof result.data.task_data === 'object' &&
      !Array.isArray(result.data.task_data)
    ) {
      task.task_data = {
        ...(result.data.task_data as Record<string, unknown>),
        ...(task.task_data as Record<string, unknown>)
      }
    } else if (!task.task_data && result.data.task_data) {
      task.task_data = result.data.task_data
    }
    task.task_source = 'claim'
    return true
  }

  private async consumeNextTaskOrClaim(): Promise<void> {
    if (!this.isIdle()) {
      return
    }

    const nextTask = this.pendingTasks.shift()
    if (nextTask) {
      await this.runEngine(nextTask)
      return
    }

    await this.requestNextTask()
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
      logger.error(
        `任务状态上报失败: taskId=${taskId} status=${taskStatus} error=${(reportError as Error)?.message || reportError}`
      )
    }
  }
}
