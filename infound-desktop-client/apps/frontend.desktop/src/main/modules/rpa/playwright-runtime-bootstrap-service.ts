import { app } from 'electron'
import { getPlaywrightBrowserPath } from '@infound/desktop-rpa'
import { logger } from '../../utils/logger'

class PlaywrightRuntimeBootstrapService {
  private warmupPromise: Promise<void> | null = null

  public async ensureBrowserReady(): Promise<void> {
    if (this.warmupPromise) {
      return this.warmupPromise
    }

    this.warmupPromise = this.doEnsureBrowserReady().catch((error) => {
      this.warmupPromise = null
      throw error
    })
    return this.warmupPromise
  }

  private async doEnsureBrowserReady(): Promise<void> {
    if (!app.isPackaged) {
      logger.info('开发模式跳过 Playwright 浏览器预解压')
      return
    }

    logger.info('开始预热 Playwright 浏览器资源')
    const results = await Promise.allSettled([
      getPlaywrightBrowserPath(false),
      getPlaywrightBrowserPath(true)
    ])

    const fullResult = results[0]
    const headlessResult = results[1]

    const failures = results
      .filter((result): result is PromiseRejectedResult => result.status === 'rejected')
      .map((result) => (result.reason instanceof Error ? result.reason.message : String(result.reason || 'unknown error')))

    if (failures.length) {
      throw new Error(`Playwright 浏览器预热失败: ${failures.join(' | ')}`)
    }

    const fullPath = fullResult.status === 'fulfilled' ? fullResult.value : ''
    const headlessPath = headlessResult.status === 'fulfilled' ? headlessResult.value : ''
    logger.info(
      `Playwright 浏览器资源预热完成: full=${fullPath || '(empty)'} headless=${headlessPath || '(empty)'}`
    )
  }
}

export const playwrightRuntimeBootstrapService = new PlaywrightRuntimeBootstrapService()
