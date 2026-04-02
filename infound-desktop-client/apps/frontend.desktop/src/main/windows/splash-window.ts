import path from 'path'
import { BrowserWindow } from 'electron'
import { is } from '@electron-toolkit/utils'
import { logger } from '../utils/logger'
import { AppConfig } from '@common/app-config'
import { MonitorController } from '../modules/ipc/monitor-controller'
import { getFilePath } from '../utils/path-helper'
import { ResourceFactory } from '../utils/resource-factory'

interface SplashState {
  percent: number
  statusCode: string
}

export const splashStatusMap: Record<string, SplashState> = {
  INIT_APP: { percent: 10, statusCode: '初始化' },
  LOAD_CORE_MODULES: { percent: 30, statusCode: '加载模块' },
  CONFIG_APP_ENV: { percent: 50, statusCode: '配置环境' },
  PREPARE_UI: { percent: 70, statusCode: '准备界面' },
  COMPLETE_STARTUP: { percent: 90, statusCode: '启动完成' }
}

export class SplashWindow {
  private splashWindow: BrowserWindow | null = null

  constructor() {
    this.splashWindow = null
  }

  public async initWindow(): Promise<void> {
    this.splashWindow = new BrowserWindow({
      width: 600,
      height: 400,
      icon: ResourceFactory.getTrayIcon(),
      frame: false, // 无边框窗口
      resizable: false,
      center: true,
      show: false, // 创建后先隐藏
      autoHideMenuBar: true,
      maximizable: true,
      minimizable: true,
      skipTaskbar: true,
      webPreferences: {
        preload: path.join(getFilePath(), '../preload/index.cjs'),
        webSecurity: false,
        sandbox: false,
        devTools: !AppConfig.IS_PRO,
        partition: 'persist:splash'
      }
    })

    this.splashWindow.once('ready-to-show', () => {
      this.splashWindow?.show()
    })

    this.splashWindow.setMenuBarVisibility(false)
    this.splashWindow.setMenu(null)

    if (is.dev && process.env['ELECTRON_RENDERER_URL']) {
      await this.splashWindow.loadURL(`${process.env['ELECTRON_RENDERER_URL']}/splash.html`)
    } else {
      await this.splashWindow.loadFile(path.join(getFilePath(), '../renderer/splash.html'))
    }

    logger.info('SplashWindow 初始化成功')
  }

  public updateProgress(state: SplashState): void {
    if (this.splashWindow) {
      const payload = { percent: state.percent, status: state.statusCode }
      MonitorController.getInstance().syncAppSplashWindowState(this.splashWindow.webContents, payload)
    }
  }

  public closeWindow(): void {
    if (this.splashWindow) {
      this.splashWindow.close()
      this.splashWindow = null!
    }
  }
}
