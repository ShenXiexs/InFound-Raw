import { AbstractWorkerManager } from '../abstract-worker-manager'
import { TaskInfo, TaskType } from '../../../services/task-service'
import { desktopRpaExecutionService } from '../desktop-rpa-execution-service'
import { resolveCreatorDetailTaskInput, waitForTaskLoginState } from '../task-input-resolver'

export class CreatorDetailWorkerManager extends AbstractWorkerManager {
  private static readonly TASK_TIMEOUT_MS = 10 * 60 * 1000

  protected get taskType(): TaskType {
    return TaskType.CreatorDetail
  }

  protected get taskTimeoutMs(): number {
    return CreatorDetailWorkerManager.TASK_TIMEOUT_MS
  }

  protected async run(task: TaskInfo): Promise<void> {
    await waitForTaskLoginState(task, { isCancelled: () => this.isCancellationRequested() })
    const { session, payload } = resolveCreatorDetailTaskInput(task)
    await desktopRpaExecutionService.startSession(session)
    await desktopRpaExecutionService.runCreatorDetail(payload, session)
  }

  protected async abortCurrentTask(): Promise<void> {
    await desktopRpaExecutionService.abortCreatorDetail()
  }
}
