import { claimTaskAsync, heartbeatAsync, reportAsync, TaskInfo, TaskStatus, TaskType } from '../../services/task-service'
import { logger } from '../../utils/logger'
import { WorkerStatus } from './task-type'

export abstract class AbstractWorkerManager {
  protected status: WorkerStatus = WorkerStatus.IDLE

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

  // 子类必须实现具体的任务执行逻辑
  protected abstract run(task: TaskInfo): Promise<void>

  protected async requestNextTask(): Promise<void> {
    if (!this.isIdle()) {
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

    // 开启心跳上报定时器 (每30秒)
    const heartbeatTimer = setInterval(() => {
      void this.sendHeartbeat(task.id)
    }, 30000)

    try {
      await this.run(task)
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
      await this.requestNextTask() // 闭环：尝试拉取下一个积压任务
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
      logger.error(
        `任务状态上报失败: taskId=${taskId} status=${taskStatus} error=${(reportError as Error)?.message || reportError}`
      )
    }
  }
}
