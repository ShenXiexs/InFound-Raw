import { logger } from '../../utils/logger'

class ExceptionHandler {
  /*registerModule(): void {
    ipcManager.registerAsync(
      IPCChannel.APP_RENDERER_EXCEPTION_THROW,
      (error: Error, additionalInfo?: Record<string, any> | undefined): Promise<void> => {
        logger.error('Renderer Process Error:', error, additionalInfo)
        return Promise.resolve()
      }
    )
  }*/

  handleMainProcessError(error: Error, additionalInfo?: Record<string, any>): void {
    logger.error('Main Process Error:', error, additionalInfo)
    //dialog.showErrorBox('程序出现错误', '程序运行出错，已记录日志，请重启应用或联系技术支持。')
  }
}

export const exceptionHandler = new ExceptionHandler()
