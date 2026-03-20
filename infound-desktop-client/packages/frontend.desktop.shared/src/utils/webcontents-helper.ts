import { LoggerService } from '../logger/logger-service'

const monitorNavigation = (logger: LoggerService, webContents: Electron.WebContents) => {
  webContents.on('did-start-navigation', (_event, url) => {
    logger.info(`[did-start-navigation] 监测到导航请求: ${url}, 此方法不能拦截`)
  })
  ;(webContents as any).on('will-frame-navigate', (_event: any, url: string) => {
    logger.info(`[will-frame-navigate] 监测到导航请求: ${url}`)
  })

  webContents.on('will-navigate', (_event, url) => {
    logger.info(`[will-navigate] 监测到导航请求: ${url}`)
  })

  webContents.on('will-redirect', (_event, url) => {
    logger.info(`[will-redirect] 监测到导航请求: ${url}`)
  })

  webContents.on('will-redirect', (_event, url) => {
    logger.info(`[will-redirect] 监测到导航请求: ${url}`)
  })
}

export { monitorNavigation }
