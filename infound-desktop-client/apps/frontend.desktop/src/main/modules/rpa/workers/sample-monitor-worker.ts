import { AbstractWorkerManager } from '../abstract-worker-manager'
import { TaskInfo, TaskType } from '../../../services/task-service'
import { desktopRpaExecutionService } from '../desktop-rpa-execution-service'
import { resolveSampleTaskInput, waitForTaskLoginState } from '../task-input-resolver'

export class SampleMonitorWorker extends AbstractWorkerManager {
  private static readonly TASK_TIMEOUT_MS = 2 * 60 * 60 * 1000

  protected get taskType(): TaskType {
    return TaskType.SampleMonitor
  }

  protected get taskTimeoutMs(): number {
    return SampleMonitorWorker.TASK_TIMEOUT_MS
  }

  protected async run(task: TaskInfo): Promise<void> {
    await waitForTaskLoginState(task, { isCancelled: () => this.isCancellationRequested() })
    const { session, payload } = resolveSampleTaskInput(task)
    await desktopRpaExecutionService.startSession(session)
    await desktopRpaExecutionService.runSampleManagement(payload, session)
  }

  protected async abortCurrentTask(): Promise<void> {
    await desktopRpaExecutionService.abortSampleManagement()
  }
}
