import { BrowserContext } from 'playwright-core'
import { chromium } from 'playwright-extra'
import StealthPlugin from 'puppeteer-extra-plugin-stealth'
import { ExecutionContext, RPAAction, RPATask } from './rpa-type'
import { LoggerService } from '../logger/logger-service'
import { ActionManager } from './action-manager'
import path from 'path'
import { getCurrentDateFormatted } from '../utils/date-helper'

export class AutomationRunner {
  private readonly logger: LoggerService
  private task: RPATask
  private actionManager: ActionManager
  private browserContext!: BrowserContext

  // TODO: 需要根据用户的真实操作系统选择对应系统的 UserAgent
  private userAgents = [
    // Google Chrome 系列 (Chromium 内核，Playwright chromium 直接适配)
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36', // Chrome + Win10/Win11 64位
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36', // Chrome + MacOS (Intel/M1/M2/M3)

    // Microsoft Edge 系列 (Chromium 内核，Playwright chromium 直接适配)
    'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.2210.91', // Edge + Win10/Win11 64位
    'Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36 Edg/120.0.2210.91' // Edge + MacOS (Intel/M1/M2/M3)
  ]

  constructor(logger: LoggerService, task: RPATask) {
    this.logger = logger
    this.task = task
    this.actionManager = new ActionManager(logger)
  }

  public async initContextAsync(userDataDir: string, browserPath: string, headless: boolean) {
    const stealth = StealthPlugin()

    // 移除可能影响布局和窗口感知的模块
    stealth.enabledEvasions.delete('iframe.contentWindow')
    stealth.enabledEvasions.delete('window.outerdimensions')

    chromium.use(stealth)

    const userAgent = this.generateRandomUserAgent()

    this.browserContext = await chromium.launchPersistentContext(path.resolve(userDataDir), {
      executablePath: browserPath,
      headless: headless,
      viewport: { width: 1440, height: 960 },
      deviceScaleFactor: 1.0,
      isMobile: false,
      userAgent: userAgent,
      args: ['--disable-blink-features=AutomationControlled', '--disable-infobars', '--no-sandbox'],
      permissions: [
        'geolocation',
        'notifications',
        'camera',
        'microphone',
        'clipboard-read',
        'clipboard-write',
        'storage-access'
      ],
      ignoreHTTPSErrors: true,
      javaScriptEnabled: true
    })
  }

  public async execute(): Promise<boolean> {
    if (this.task.config.enableTrace) {
      await this.browserContext.tracing.start({
        screenshots: true,
        snapshots: true,
        sources: true
      })
    }

    const page = await this.browserContext.newPage()
    let success = false
    try {
      for (const step of this.task.steps) {
        success = await this.runStep({ page, data: {} }, step)
      }
    } catch (error) {
      this.logger.error(`执行流程失败: ${(error as Error).message}`)
    } finally {
      if (success) {
        await this.browserContext.tracing.stop()
      } else {
        const fileName = `trace/${getCurrentDateFormatted()}/${this.task.taskId}.zip`
        await this.browserContext.tracing.stop({
          path: path.join(process.cwd(), fileName) // 对应 Paths.get
        })
        this.logger.error(`保存 trace 文件：${fileName}`)
      }
      this.logger.info(`任务结束`)
    }
    return success
  }

  public async runStep(context: ExecutionContext, action: RPAAction): Promise<boolean> {
    let attempts = 0
    const maxRetries = action.options?.retryCount || 2

    while (attempts <= maxRetries) {
      try {
        const executor = this.actionManager.getExecutor(action.actionType)
        if (!executor) throw new Error(`Unknown action: ${action.actionType}`)

        await executor.execute(context, action)
        return true
      } catch (error) {
        attempts++
        if (action.onError === 'abort' || attempts > maxRetries) {
          throw error // 向上抛出错误，中断任务流
        }
      }
    }

    this.logger.warn(`步骤未成功执行完成`)
    return false
  }

  private generateRandomUserAgent(): string {
    return this.userAgents[Math.floor(Math.random() * this.userAgents.length)]
  }
}
