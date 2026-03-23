import { AbstractWorkerManager } from '../abstract-worker-manager'
import { TaskInfo, TaskType } from '../../../services/task-service'
import { desktopRpaExecutionService } from '../desktop-rpa-execution-service'
import { resolveSampleTaskInput } from '../task-input-resolver'

export class SampleMonitorWorker extends AbstractWorkerManager {
  protected get taskType(): TaskType {
    return TaskType.SampleMonitor
  }

  protected async run(task: TaskInfo): Promise<void> {
    const { session, payload } = resolveSampleTaskInput(task)
    await desktopRpaExecutionService.startSession(session)
    await desktopRpaExecutionService.runSampleManagement(payload)
  }
}
