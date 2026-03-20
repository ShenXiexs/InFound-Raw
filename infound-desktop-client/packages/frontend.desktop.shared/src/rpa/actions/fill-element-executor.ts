import { IActionExecutor } from '../i-action-executor'
import { LoggerService } from '../../logger/logger-service'
import { ExecutionContext, FillElementPayload, RPAAction } from '../rpa-type'
import { LocatorEngine } from '../engines/locator-engine'

export class FillElementExecutor implements IActionExecutor<FillElementPayload> {
  private readonly logger: LoggerService

  constructor(logger: LoggerService) {
    this.logger = logger
  }

  async execute(
    context: ExecutionContext,
    action: RPAAction & { payload: FillElementPayload }
  ): Promise<boolean> {
    this.logger.info(`执行填充元素动作：${action.payload.locator.value}`)

    const { payload } = action
    const { page } = context
    const locator = LocatorEngine.build(
      payload.locator?.frame ? page.frameLocator(payload.locator.frame) : page,
      payload.locator
    )
    if (!locator) {
      throw new Error(`元素 selector=${payload.locator!.value} 不存在`)
    }

    // 1. 等待交互就绪（比单纯 visible 更准）
    await locator.waitFor({ state: 'attached', timeout: 15000 })

    // 2. 滚动到可视区域（防止在底部不可见导致点击失败）
    await locator.scrollIntoViewIfNeeded()

    // 获取当前值并清空 (模拟退格)
    const currentValue = await locator.inputValue().catch(() => '')
    await locator.focus({ timeout: 3000 })

    if (currentValue) {
      await page.keyboard.press('End')
      for (let i = 0; i < currentValue.length; i++) {
        await page.keyboard.press('Backspace')
      }
    }

    // 逐字输入，随机延迟 200ms - 450ms
    for (const char of payload.value!) {
      await page.keyboard.type(char, {
        delay: Math.random() * (450 - 200) + 200
      })
    }

    await page.waitForTimeout(2000)

    if (payload.afterKey) {
      await page.keyboard.press(payload.afterKey)
    }

    await page.waitForTimeout(Math.random() * (3000 - 1500) + 1500)
    this.logger.info(`完成输入：${payload.locator!.value}`)

    return true
  }
}
