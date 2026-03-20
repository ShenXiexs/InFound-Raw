import { ActionPayloadMap } from './rpa-type'
import { IActionExecutor } from './i-action-executor'
import { ClickElementExecutor } from './actions/click-element-executor'
import { LoggerService } from '../logger/logger-service'
import { FillElementExecutor } from './actions/fill-element-executor'
import { GotoExecutor } from './actions/goto-executor'

export class ActionManager {
  private executorStrategies: Partial<{
    [K in keyof ActionPayloadMap]: IActionExecutor<ActionPayloadMap[K]>
  }> = {}

  constructor(logger: LoggerService) {
    this.executorStrategies.goto = new GotoExecutor(logger)
    this.executorStrategies.clickElement = new ClickElementExecutor(logger)
    this.executorStrategies.fillElement = new FillElementExecutor(logger)
  }

  getExecutor<K extends keyof ActionPayloadMap>(
    actionType: K
  ): IActionExecutor<ActionPayloadMap[K]> {
    const executor = this.executorStrategies[actionType]
    if (!executor) throw new Error(`Action ${actionType} not implemented`)
    return executor
  }
}
