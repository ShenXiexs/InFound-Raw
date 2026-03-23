import { AbstractWorkerManager } from '../abstract-worker-manager'
import { TaskInfo, TaskType } from '../../../services/task-service'
import { desktopRpaExecutionService } from '../desktop-rpa-execution-service'
import { resolveChatTaskInput } from '../task-input-resolver'

export class ChatWorkerManager extends AbstractWorkerManager {
  protected get taskType(): TaskType {
    return TaskType.Chat
  }

  protected async run(task: TaskInfo): Promise<void> {
    const { session, payload } = resolveChatTaskInput(task)
    await desktopRpaExecutionService.startSession(session)
    await desktopRpaExecutionService.runChatbot(payload)
  }
}
