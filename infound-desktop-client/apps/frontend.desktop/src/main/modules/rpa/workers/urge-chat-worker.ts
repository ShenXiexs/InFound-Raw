import { AbstractWorkerManager } from '../abstract-worker-manager'
import { TaskInfo, TaskType } from '../../../services/task-service'
import { desktopRpaExecutionService } from '../desktop-rpa-execution-service'
import { resolveUrgeChatTaskInput, waitForTaskLoginState } from '../task-input-resolver'

export class UrgeChatWorkerManager extends AbstractWorkerManager {
  private static readonly TASK_TIMEOUT_MS = 10 * 60 * 1000

  protected get taskType(): TaskType {
    return TaskType.UrgeChat
  }

  protected get taskTimeoutMs(): number {
    return UrgeChatWorkerManager.TASK_TIMEOUT_MS
  }

  protected async run(task: TaskInfo): Promise<void> {
    await waitForTaskLoginState(task, { isCancelled: () => this.isCancellationRequested() })
    const { session, payload } = resolveUrgeChatTaskInput(task)
    await desktopRpaExecutionService.startSession(session)
    await desktopRpaExecutionService.runUrgeChat(payload, session)
  }

  protected async abortCurrentTask(): Promise<void> {
    await desktopRpaExecutionService.abortChatbot()
  }
}
