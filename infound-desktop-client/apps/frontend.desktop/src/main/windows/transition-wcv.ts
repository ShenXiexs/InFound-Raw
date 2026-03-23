import { app, BrowserWindow, WebContentsView } from 'electron'
import { join } from 'path'
import { AppConfig } from '@common/app-config'
import { resetWCVSize, resetWCVSizeToZero } from '../utils/mcv-helper'
import { logger } from '../utils/logger'

export class TransitionWcv {
  public transitionWcv: WebContentsView | null = null
  private readonly baseWindow: BrowserWindow | null = null
  private isVisible: boolean = false

  constructor(baseWindow: BrowserWindow) {
    this.baseWindow = baseWindow
    this.transitionWcv = null
  }

  public async initView(): Promise<void> {
    // 初始化过渡页面视图
    this.transitionWcv = new WebContentsView({
      webPreferences: {
        nodeIntegration: false, //设置为true时，允许在Web页面中使用Node.js API。默认情况下，这个选项是禁用的，以提高安全性。
        webSecurity: false, //设置为false时，禁用同源策略，允许加载来自不同源的资源。
        preload: join(__dirname, '../preload/index.cjs'),
        backgroundThrottling: false,
        devTools: !AppConfig.IS_PRO,
        sandbox: false, //sandbox选项设置为true时，WebContentsView将在一个受限的环境中运行Web页面
        //webgl: false, // WhatsApp 无需 3D
        plugins: false, // 禁用 Flash 等插件
        enableWebSQL: false, // 禁用废弃的 WebSQL
        enablePreferredSizeMode: true, // 按需渲染
        disableHtmlFullscreenWindowResize: true
      }
    })

    resetWCVSizeToZero(this.transitionWcv)

    if (!app.isPackaged && process.env['ELECTRON_RENDERER_URL']) {
      await this.transitionWcv.webContents.loadURL(`${process.env['ELECTRON_RENDERER_URL']}/universal.html#/loading`)
    } else {
      // 生产环境：先加载文件，然后通过路由导航
      await this.transitionWcv.webContents.loadFile(join(__dirname, '../renderer/universal.html'))
      // 如果需要导航到特定路由，可以通过 JavaScript 实现
      await this.transitionWcv.webContents.executeJavaScript(`
        window.location.hash = '#/loading';
      `)
    }
  }

  public isShowing(): boolean {
    return this.transitionWcv ? this.transitionWcv.getVisible() : false
  }

  public showTransitionLoadingWCV(): void {
    if (this.transitionWcv && this.baseWindow && !this.isVisible) {
      if (!this.baseWindow.contentView.children.includes(this.transitionWcv)) {
        this.baseWindow!.contentView.addChildView(this.transitionWcv)
        resetWCVSize(this.baseWindow!, this.transitionWcv)
        this.isVisible = true
        logger.info('showTransitionLoadingWCV: added')
      }
    }
  }

  public displayTransitionLoadingWCV(): void {
    //added by Phoenix：hide loading window
    if (this.transitionWcv && this.baseWindow && this.isVisible) {
      logger.info('Removing transitionWcv, current children:', this.baseWindow.contentView.children.length)
      this.baseWindow.contentView.removeChildView(this.transitionWcv)
      resetWCVSizeToZero(this.transitionWcv)
      this.isVisible = false
      logger.info('After removal, children:', this.baseWindow.contentView.children.length)
    }
  }

  public closeTransitionWCV(): void {
    if (this.transitionWcv && this.baseWindow) {
      this.displayTransitionLoadingWCV() // 先隐藏
      resetWCVSizeToZero(this.transitionWcv)
      this.transitionWcv.webContents.close()
      this.baseWindow.contentView.removeChildView(this.transitionWcv)
      this.transitionWcv = null
      logger.info('closeTransitionWCV: destroyed')
    }
  }

  public openTransitionWCV(params: Record<string, any>): void {
    this.transitionWcv?.webContents
      .executeJavaScript(
        `
        window.location.hash = '#${params['routerPath']}';
      `
      )
      .then(() => {})
  }
}
