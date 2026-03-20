import { BaseWindow, session, WebContentsView } from 'electron'
import { logger } from '../utils/logger'
import { AppConfig } from '@common/app-config'
import path from 'path'

export class TkWcv {
  private baseWindow: BaseWindow | null = null
  private tkWCV: WebContentsView | null = null

  constructor() {
    this.baseWindow = null
    this.tkWCV = null
  }

  public async initView(baseWindow: BaseWindow): Promise<void> {
    this.baseWindow = baseWindow

    const persistKey = 'persist:TKWindow'
    const sess = session.fromPartition(persistKey)

    sess.webRequest.onBeforeRequest((details, callback) => {
      if (details.url.startsWith('bytedance://')) {
        logger.info('拦截 bytedance 协议')
        return callback({ cancel: true })
      }
      callback({ cancel: false })
    })

    this.tkWCV = new WebContentsView({
      webPreferences: {
        partition: persistKey,
        preload: path.join(AppConfig.DIR_NAME, '../preload/index.js'),
        session: sess,
        devTools: !AppConfig.IS_PRO,
        contextIsolation: true, // 强制开启，防止网页 JS 访问主进程模块
        nodeIntegration: false, // 严禁 Node.js 环境
        sandbox: false, // 开启沙盒，这是防止调用系统底层 Shell 的最强防线
        safeDialogs: true,
        webSecurity: true,
        allowRunningInsecureContent: false,
        plugins: false, // 严禁插件，防止插件触发系统调用
        webviewTag: false // 禁用 webview 标签
      }
    })

    this.tkWCV.webContents.setUserAgent(AppConfig.USER_AGENT)

    //monitorNavigation(logger, this.tkWCV.webContents)
    ;(this.tkWCV.webContents as any).on('will-frame-navigate', (event, url) => {
      if (!url.startsWith('http') && !url.startsWith('https')) {
        logger.warn(`拦截到子框架的协议跳转: ${url}`)
        event.preventDefault() // 这一步在子框架中同样有效
      }
    })

    // 监听渲染进程崩溃
    this.tkWCV.webContents.on('render-process-gone', (_event: Electron.Event, details: Electron.RenderProcessGoneDetails) => {
      const { reason } = details
      logger.error(`渲染进程崩溃: ${reason === 'killed' ? '被杀死' : '意外崩溃'}`)
      logger.error(`崩溃页面: ${this.tkWCV?.webContents.getURL()}`)
    })

    // 监听渲染进程无响应
    this.tkWCV.webContents.on('unresponsive', () => {
      logger.error('渲染进程无响应')
    })

    this.tkWCV.setVisible(false)

    //await this.tkWCV.webContents.loadURL('https://seller-mx.tiktok.com/')

    this.baseWindow.contentView.addChildView(this.tkWCV)

    logger.info('TKWindow 初始化成功')
  }

  public async openView(url: string | null): Promise<void> {
    this.baseWindow!.contentView.addChildView(this.tkWCV!)

    try {
      if (url) await this.tkWCV!.webContents.loadURL(url)
    } catch (err) {
      logger.error('加载失败，尝试重新初始化 session 或清理缓存...')
      // 如果失败，考虑清除缓存或 partition
      await this.tkWCV!.webContents.session.clearCache()
    }

    this.resize()
  }

  public getWebContentsView(): WebContentsView {
    return this.tkWCV!
  }

  public resize(): void {
    const [contentWidth, contentHeight] = this.baseWindow!.getContentSize()

    this.tkWCV!.setBounds({
      x: 0,
      y: 120,
      width: contentWidth,
      height: contentHeight - 120
    })

    if (!this.tkWCV!.getVisible()) {
      this.tkWCV!.setVisible(true)
    }
  }
}
