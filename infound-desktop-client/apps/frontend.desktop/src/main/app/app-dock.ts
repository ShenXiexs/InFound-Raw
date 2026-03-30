import { logger } from '../utils/logger'
import { app, Menu } from 'electron'
import { appWindowsAndViewsManager } from '../windows/app-windows-and-views-manager'

export class AppDock {
  private static instance: AppDock | null = null

  private constructor() {
    // 私有构造函数，防止外部直接 new
  }

  /**
   * 获取单例实例
   */
  public static getInstance(): AppDock {
    if (!AppDock.instance) {
      AppDock.instance = new AppDock()
    }
    return AppDock.instance
  }

  /**
   * 初始化托盘
   */
  public setup(): void {
    // 1. 判断是否为 macOS 平台
    if (process.platform !== 'darwin') return

    try {
      // 2. 定义菜单模板
      const dockMenu = Menu.buildFromTemplate([
        {
          label: '退出应用',
          click: (): void => {
            this.quitApp()
          }
        }
      ])

      // 3. 设置 Dock 菜单
      app.dock?.setMenu(dockMenu)
    } catch (error) {
      logger.error('创建程序坞菜单失败:', error)
    }
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
