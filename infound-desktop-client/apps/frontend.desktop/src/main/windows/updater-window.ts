import { BrowserWindow } from 'electron'
import { ResourceFactory } from '../utils/resource-factory'
import path from 'path'
import { getFilePath } from '../utils/path-helper'
import { AppConfig } from '@common/app-config'
import { is } from '@electron-toolkit/utils'
import { logger } from '../utils/logger'

export class UpdaterWindow {
  private updaterWindow: BrowserWindow | null = null

  constructor() {
    this.updaterWindow = null
  }

  public async initWindow(): Promise<void> {
    this.updaterWindow = new BrowserWindow({
      width: 600,
      height: 450,
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
        partition: 'persist:updater'
      }
    })

    this.updaterWindow.once('ready-to-show', () => {
      this.updaterWindow?.show()
    })

    this.updaterWindow.setMenuBarVisibility(false)
    this.updaterWindow.setMenu(null)

    if (is.dev && process.env['ELECTRON_RENDERER_URL']) {
      await this.updaterWindow.loadURL(`${process.env['ELECTRON_RENDERER_URL']}/updater.html`)
    } else {
      await this.updaterWindow.loadFile(path.join(getFilePath(), '../renderer/updater.html'))
    }

    logger.info('UpdaterWindow 初始化成功')
  }

  public closeWindow(): void {
    if (this.updaterWindow) {
      this.updaterWindow.close()
      this.updaterWindow = null!
    }
  }
}
