import { IActionExecutor } from '../i-action-executor'
import { LoggerService } from '../../logger/logger-service'
import { ClickElementPayload, ExecutionContext, RPAAction } from '../rpa-type'
import { LocatorEngine } from '../engines/locator-engine'
import { HumanInteractionEngine } from '../engines/human-interaction-engine'

export class ClickElementExecutor implements IActionExecutor<ClickElementPayload> {
  private readonly logger: LoggerService

  constructor(logger: LoggerService) {
    this.logger = logger
  }

  async execute(
    context: ExecutionContext,
    action: RPAAction & { payload: ClickElementPayload }
  ): Promise<boolean> {
    this.logger.info(`执行点击元素动作：${action.payload.locator!.value}`)

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

    const box = await locator.boundingBox()
    if (!box) {
      throw new Error(`元素 selector=${payload.locator!.value} 无布局信息，可能已隐藏/脱离 DOM`)
    }

    // 4. 更加智能的坐标点：避开边缘 (Padding 策略)
    const padding = 5
    const targetX = box.x + padding + Math.random() * Math.max(box.width - 2 * padding, 1)
    const targetY = box.y + padding + Math.random() * Math.max(box.height - 2 * padding, 1)

    // 5. 执行平滑移动
    await HumanInteractionEngine.moveTo(page, targetX, targetY)

    // 6. 尝试点击，如果由于重叠被遮挡，通过 JS 强力触发
    const maxRetries = action.options?.retryCount || 2
    let attempt = 0
    while (attempt <= maxRetries) {
      try {
        await locator.click({
          position: { x: targetX - box.x, y: targetY - box.y },
          timeout: 5123
        })
        break
      } catch (error) {
        attempt++
        this.logger.warn(`常规点击失败，报错信息: ${(error as Error).message}`)
        if (attempt > 0) {
          // 每次重试前，尝试关闭可能遮挡的全局弹窗
          await context.page.keyboard.press('Escape')
          await context.page.waitForTimeout(500)
        }
        if (attempt === 2) {
          this.logger.warn('重试多次未果，触发页面强制刷新')
          await context.page.reload()
        }
        if (attempt > maxRetries) {
          await this.handleFinalFailure(context, action, error)
          throw new Error(`元素 selector=${payload.locator!.value} 点击失败`)
        }
        const delay = Math.pow(2, attempt) * 500
        this.logger.info(`等待 ${delay}ms 后进行第 ${attempt + 1} 次重试...`)
        await new Promise((resolve) => setTimeout(resolve, delay))
      }
    }

    this.logger.info(`完成点击：${payload.locator!.value}`)

    return true
  }

  private async handleFinalFailure(context: ExecutionContext, action: RPAAction, error: any) {
    const fileName = `error-${Date.now()}.png`
    await context.page.screenshot({ path: `./logs/screenshots/${fileName}` })
    this.logger.error(`任务执行最终失败，已截屏保存至: ${fileName}`)
  }
}
