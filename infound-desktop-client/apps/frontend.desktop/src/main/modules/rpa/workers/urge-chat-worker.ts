import { AbstractWorkerManager } from '../abstract-worker-manager'
import { TaskInfo, TaskType } from '../../../services/task-service'
import { desktopRpaExecutionService } from '../desktop-rpa-execution-service'
import { resolveUrgeChatTaskInput } from '../task-input-resolver'

export class UrgeChatWorkerManager extends AbstractWorkerManager {
  protected get taskType(): TaskType {
    return TaskType.UrgeChat
  }

  protected async run(task: TaskInfo): Promise<void> {
    const { session, payload } = resolveUrgeChatTaskInput(task)
    await desktopRpaExecutionService.startSession(session)
    await desktopRpaExecutionService.runUrgeChat(payload)
  }

  protected async abortCurrentTask(): Promise<void> {
    await desktopRpaExecutionService.abortChatbot()
  }
}
