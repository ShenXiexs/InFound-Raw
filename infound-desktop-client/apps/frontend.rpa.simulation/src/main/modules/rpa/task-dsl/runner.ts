import { TaskDefinition, TaskLoggerLike, TaskStepBase } from './types'

type TaskActionType<Action extends TaskStepBase> = Action['actionType']
type TaskActionHandler<Action extends TaskStepBase, Type extends string> = (
  action: Extract<Action, { actionType: Type }>,
  context: { taskId: string; taskName: string; stepIndex: number; data: Record<string, unknown> }
) => Promise<void>

export type TaskActionHandlerMap<Action extends TaskStepBase> = {
  [K in TaskActionType<Action> & string]: TaskActionHandler<Action, K>
}

const stringifyValue = (value: unknown): string => {
  if (value === null || value === undefined) return ''
  if (Array.isArray(value)) return value.map((item) => String(item)).join(',')
  return String(value)
}

const describeStep = (step: TaskStepBase): string => {
  const stepId = String(step.id || '').trim()
  const payload = ((step as TaskStepBase & { payload?: Record<string, unknown> }).payload ?? {}) as Record<string, unknown>
  const actionType = String(step.actionType || 'unknown')

  const detail = (() => {
    switch (actionType) {
      case 'goto':
        return `url=${stringifyValue(payload.url)}`
      case 'clickByText':
        return `text=${stringifyValue(payload.text)}`
      case 'clickSelector':
        return `selector=${stringifyValue(payload.selector)}`
      case 'fillSelector':
        return `selector=${stringifyValue(payload.selector)} value=${stringifyValue(payload.value)}`
      case 'setCheckbox':
        return `selector=${stringifyValue(payload.selector)} checked=${stringifyValue(payload.checked ?? true)}`
      case 'selectDropdownSingle':
        return `trigger=${stringifyValue(payload.triggerText)} option=${stringifyValue(payload.optionText)}`
      case 'selectDropdownMultiple':
        return `trigger=${stringifyValue(payload.triggerText)} options=${stringifyValue(payload.optionTexts)}`
      case 'selectCascaderOptionsByValue':
        return `trigger=${stringifyValue(payload.triggerText)} values=${stringifyValue(payload.values)}`
      case 'fillDropdownRange':
        return `trigger=${stringifyValue(payload.triggerText)} min=${stringifyValue(payload.minValue)} max=${stringifyValue(payload.maxValue)}`
      case 'fillDropdownThreshold':
        return `trigger=${stringifyValue(payload.triggerText)} value=${stringifyValue(payload.value)}`
      case 'waitForBodyText':
        return `text=${stringifyValue(payload.text)}`
      case 'waitForSelector':
        return `selector=${stringifyValue(payload.selector)} state=${stringifyValue(payload.state ?? 'present')}`
      case 'pressKey':
        return `key=${stringifyValue(payload.key)}`
      case 'assertUrlContains':
        return `keyword=${stringifyValue(payload.keyword)}`
      case 'readText':
        return `selector=${stringifyValue(payload.selector)} saveAs=${stringifyValue(payload.saveAs)}`
      case 'collectApiItemsByScrolling':
        return `captureKey=${stringifyValue(payload.captureKey)} saveAs=${stringifyValue(payload.saveAs)}`
      default:
        return ''
    }
  })()

  if (stepId && detail) {
    return `${actionType} [${stepId}] ${detail}`
  }
  if (stepId) {
    return `${actionType} [${stepId}]`
  }
  if (detail) {
    return `${actionType} ${detail}`
  }
  return actionType
}

export class TaskDSLRunner<Action extends TaskStepBase> {
  constructor(private readonly logger: TaskLoggerLike) {}

  public async execute(task: TaskDefinition<Action>, handlers: TaskActionHandlerMap<Action>): Promise<Record<string, unknown>> {
    this.logger.info(`[${task.taskId}] 开始执行任务: ${task.taskName}`)
    const runtimeData: Record<string, unknown> = {}

    for (let stepIndex = 0; stepIndex < task.steps.length; stepIndex += 1) {
      const step = task.steps[stepIndex]
      const stepName = String((step as { actionType?: string }).actionType || 'unknown')
      const stepDescription = describeStep(step)
      const maxRetries = Number(step.options?.retryCount ?? task.config.retryCount ?? 0)
      const onError = step.onError ?? 'abort'
      let attempt = 0

      while (attempt <= maxRetries) {
        try {
          const handler = handlers[stepName as keyof TaskActionHandlerMap<Action>] as TaskActionHandler<Action, string> | undefined
          if (!handler) {
            throw new Error(`Action handler not found: ${stepName}`)
          }

          this.logger.info(`[${task.taskId}] 执行步骤(${stepIndex + 1}/${task.steps.length}): ${stepDescription}`)
          await handler(step as Extract<Action, { actionType: string }>, {
            taskId: task.taskId,
            taskName: task.taskName,
            stepIndex: stepIndex + 1,
            data: runtimeData
          })
          break
        } catch (error) {
          attempt += 1
          const errorMessage = (error as Error)?.message || String(error)
          const canRetry = attempt <= maxRetries

          if (canRetry) {
            this.logger.warn(
              `[${task.taskId}] 步骤失败(${stepDescription})，重试 ${attempt}/${maxRetries}，原因: ${errorMessage}`
            )
            continue
          }

          if (onError === 'continue') {
            this.logger.warn(
              `[${task.taskId}] 步骤失败(${stepDescription})，已重试 ${maxRetries} 次，按 continue 策略跳过，原因: ${errorMessage}`
            )
            break
          }

          this.logger.error(`[${task.taskId}] 任务中断，失败步骤: ${stepDescription}，原因: ${errorMessage}`)
          throw error
        }
      }
    }

    this.logger.info(`[${task.taskId}] 任务执行完成: ${task.taskName}`)
    return runtimeData
  }
}
