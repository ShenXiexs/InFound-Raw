import { IActionExecutor } from '../i-action-executor'
import { LoggerService } from '../../logger/logger-service'
import { ExecutionContext, GotoPayload, RPAAction } from '../rpa-type'

export class GotoExecutor implements IActionExecutor<GotoPayload> {
  private readonly logger: LoggerService

  constructor(logger: LoggerService) {
    this.logger = logger
  }

  async execute(
    context: ExecutionContext,
    action: RPAAction & { payload: GotoPayload }
  ): Promise<boolean> {
    this.logger.info(`执行跳转动作：${action.payload.url}`)

    const { page } = context

    await page.goto(action.payload.url!, {
      waitUntil: action.payload.waitUntil || 'load',
      timeout: 30000
    })

    this.logger.info(`完成跳转：${action.payload.url}`)
    return true
  }
}
