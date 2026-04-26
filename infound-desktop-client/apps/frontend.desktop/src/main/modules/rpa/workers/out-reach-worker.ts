import { AbstractWorkerManager } from '../abstract-worker-manager'
import { TaskInfo, TaskType } from '../../../services/task-service'
import { desktopRpaExecutionService } from '../desktop-rpa-execution-service'
import { resolveOutreachTaskInput, waitForTaskLoginState } from '../task-input-resolver'
import { logger } from '../../../utils/logger'

export class OutReachWorkerManager extends AbstractWorkerManager {
  private static readonly TASK_TIMEOUT_MS = 60 * 60 * 1000

  protected get taskType(): TaskType {
    return TaskType.Outreach
  }

  protected get taskTimeoutMs(): number {
    return OutReachWorkerManager.TASK_TIMEOUT_MS
  }

  protected async run(task: TaskInfo): Promise<void> {
    logger.debug(`开始执行任务: ${task.id}`)
    await waitForTaskLoginState(task, { isCancelled: () => this.isCancellationRequested() })
    const { session, payload } = resolveOutreachTaskInput(task)
    await desktopRpaExecutionService.startSession(session)
    await desktopRpaExecutionService.runOutreach(payload, session)
  }

  protected async abortCurrentTask(): Promise<void> {
    await desktopRpaExecutionService.abortOutreach()
  }
}
