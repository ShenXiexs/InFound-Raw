import { app, Menu, Tray } from 'electron'
import * as Path from 'path'
import { appWindowsAndViewsManager } from '../windows/app-windows-and-views-manager'
import { logger } from '../utils/logger'
import { globalState } from '../modules/state/global-state'

export class AppTray {
  private static instance: AppTray | null = null
  private tray: Tray | null = null

  private constructor() {
    // 私有构造函数，防止外部直接 new
  }

  /**
   * 获取单例实例
   */
  public static getInstance(): AppTray {
    if (!AppTray.instance) {
      AppTray.instance = new AppTray()
    }
    return AppTray.instance
  }

  /**
   * 初始化托盘
   */
  public setup(): void {
    if (this.tray) {
      logger.warn('托盘实例已存在，跳过初始化')
      return
    }

    try {
      const iconPath = Path.join(globalState.currentState.appSetting.resourcesPath, 'icon.png')

      this.tray = new Tray(iconPath)
      this.tray.setToolTip('寻达')
      this.tray.setContextMenu(this.createContextMenu())

      this.bindEvents()
    } catch (error) {
      logger.error('创建托盘失败:', error)
    }
  }

  /**
   * 获取 Tray 实例（如果需要从外部操作 Tray）
   */
  public getTray(): Tray | null {
    return this.tray
  }

  /**
   * 绑定托盘事件
   */
  private bindEvents(): void {
    if (!this.tray) return

    this.tray.on('click', () => {
      // 如果不在更新中，点击图标显示窗口
      if (!globalState.currentState.isUpdating) {
        appWindowsAndViewsManager.mainWindow.showWindow()
      }
    })
  }

  /**
   * 创建右键菜单
   */
  private createContextMenu(): Menu {
    return Menu.buildFromTemplate([
      {
        label: '退出应用',
        click: (): void => {
          this.quitApp()
        }
      }
    ])
  }

  /**
   * 退出逻辑封装
   */
  private quitApp(): void {
    try {
      appWindowsAndViewsManager.mainWindow.closeWindow()
    } catch (error) {
      logger.error('退出程序时发生错误:', error)
    } finally {
      app.exit()
    }
  }
}
