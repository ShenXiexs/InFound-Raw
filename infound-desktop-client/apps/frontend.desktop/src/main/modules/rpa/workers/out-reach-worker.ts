import { AbstractWorkerManager } from '../abstract-worker-manager'
import { TaskInfo, TaskType } from '../../../services/task-service'
import { desktopRpaExecutionService } from '../desktop-rpa-execution-service'
import { resolveOutreachTaskInput } from '../task-input-resolver'

export class OutReachWorkerManager extends AbstractWorkerManager {
  protected get taskType(): TaskType {
    return TaskType.Outreach
  }

  protected async run(task: TaskInfo): Promise<void> {
    const { session, payload } = resolveOutreachTaskInput(task)
    await desktopRpaExecutionService.startSession(session)
    await desktopRpaExecutionService.runOutreach(payload)
  }

  protected async abortCurrentTask(): Promise<void> {
    await desktopRpaExecutionService.abortOutreach()
  }
}
