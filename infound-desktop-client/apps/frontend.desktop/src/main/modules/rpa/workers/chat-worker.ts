import { AbstractWorkerManager } from '../abstract-worker-manager'
import { TaskInfo, TaskType } from '../../../services/task-service'
import { desktopRpaExecutionService } from '../desktop-rpa-execution-service'
import { resolveChatTaskInput, waitForTaskLoginState } from '../task-input-resolver'

export class ChatWorkerManager extends AbstractWorkerManager {
  private static readonly TASK_TIMEOUT_MS = 10 * 60 * 1000

  protected get taskType(): TaskType {
    return TaskType.Chat
  }

  protected get taskTimeoutMs(): number {
    return ChatWorkerManager.TASK_TIMEOUT_MS
  }

  protected async run(task: TaskInfo): Promise<void> {
    await waitForTaskLoginState(task, { isCancelled: () => this.isCancellationRequested() })
    const { session, payload } = resolveChatTaskInput(task)
    await desktopRpaExecutionService.startSession(session)
    await desktopRpaExecutionService.runChatbot(payload, session)
  }

  protected async abortCurrentTask(): Promise<void> {
    await desktopRpaExecutionService.abortChatbot()
  }
}
