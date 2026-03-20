import { logger } from '../utils/logger'
import { MainWindow } from './main-window'
import { TkWcv } from './tk-wcv'

class AppWindowsAndViewsManager {
  private _mainWindow: MainWindow | null = null
  public get mainWindow(): MainWindow {
    if (!this._mainWindow) {
      throw new Error('MainWindow 尚未初始化，请先调用 initMainWindow')
    }
    return this._mainWindow
  }

  private _tkWebContentView: TkWcv | null = null
  public get tkWebContentView(): TkWcv {
    if (!this._tkWebContentView) {
      throw new Error('TKWebContentView 尚未初始化，请先调用 initTKWebContentView')
    }
    return this._tkWebContentView
  }

  public async initMainWindow(): Promise<void> {
    if (this._mainWindow) return // 防止重复初始化

    this._mainWindow = new MainWindow()
    await this._mainWindow.initWindow()

    this._tkWebContentView = new TkWcv()
    await this._tkWebContentView.initView(this._mainWindow.baseWindow!)

    logger.info('AppWindowsAndViewsManager 初始化窗口完成')
  }

  public resize(): void {
    this._tkWebContentView?.resize()
  }
}

export const appWindowsAndViewsManager = new AppWindowsAndViewsManager()
