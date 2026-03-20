import { MainWindow } from './main-window'
import { SplashWindow } from './splash-window'
import { TkShopWindowManager } from './tk-shop-window-manager'

class AppWindowsAndViewsManager {
  private readonly _mainWindow: MainWindow | null = null
  private readonly _splashWindow: SplashWindow | null = null
  private readonly _tkShopWindowManager: TkShopWindowManager | null = null

  constructor() {
    this._splashWindow = new SplashWindow()
    this._mainWindow = new MainWindow()
    this._tkShopWindowManager = new TkShopWindowManager()
  }

  public get mainWindow(): MainWindow {
    if (!this._mainWindow) {
      throw new Error('MainWindow 尚未初始化，请先调用 initMainWindow')
    }
    return this._mainWindow
  }

  public get splashWindow(): SplashWindow {
    if (!this._splashWindow) {
      throw new Error('SplashWindow 尚未初始化，请先调用 initWindow')
    }
    return this._splashWindow
  }

  public get tkShopWindowManager(): TkShopWindowManager {
    if (!this._tkShopWindowManager) {
      throw new Error('TkShopWindowManager 尚未初始化，请先调用 initTkShopWindowManager')
    }
    return this._tkShopWindowManager
  }

  public async initMainWindow(): Promise<void> {
    await this._mainWindow?.initWindow()
  }

  public mainWindowResize(): void {
    //TODO: 当主窗口尺寸改变时，调整子窗口尺寸
    return
  }
}

export const appWindowsAndViewsManager = new AppWindowsAndViewsManager()
