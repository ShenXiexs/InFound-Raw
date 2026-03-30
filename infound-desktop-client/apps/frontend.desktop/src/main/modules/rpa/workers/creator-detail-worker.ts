import { AbstractWorkerManager } from '../abstract-worker-manager'
import { TaskInfo, TaskType } from '../../../services/task-service'
import { desktopRpaExecutionService } from '../desktop-rpa-execution-service'
import { resolveCreatorDetailTaskInput } from '../task-input-resolver'

export class CreatorDetailWorkerManager extends AbstractWorkerManager {
  protected get taskType(): TaskType {
    return TaskType.CreatorDetail
  }

  protected async run(task: TaskInfo): Promise<void> {
    const { session, payload } = resolveCreatorDetailTaskInput(task)
    await desktopRpaExecutionService.startSession(session)
    await desktopRpaExecutionService.runCreatorDetail(payload)
  }

  protected async abortCurrentTask(): Promise<void> {
    await desktopRpaExecutionService.abortCreatorDetail()
  }
}
