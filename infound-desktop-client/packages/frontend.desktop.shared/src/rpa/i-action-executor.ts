import { ExecutionContext, RPAAction } from './rpa-type'

export interface IActionExecutor<T = any> {
  execute(context: ExecutionContext, action: RPAAction & { payload: T }): Promise<boolean>
}
