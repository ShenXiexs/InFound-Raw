import path from 'path'
import { app, BrowserWindow, Menu } from 'electron'
import { AppConfig } from '@common/app-config'
import { initializeLogger, logger } from '../utils/logger'
import { appWindowsAndViewsManager } from '../windows/app-windows-and-views-manager'
import { globalState } from '../modules/state/global-state'
import { AppTray } from './app-tray'
import { electronApp } from '@electron-toolkit/utils'
import { IPCManager } from '../modules/ipc/base/ipc-manager'
import { LoggerController } from '../modules/ipc/logger-controller'
import { GlobalStateController } from '../modules/ipc/global-state-controller'
import { AppController } from '../modules/ipc/app-controller'
import { MonitorController } from '../modules/ipc/monitor-controller'
import { TkShopController } from '../modules/ipc/tk-shop-controller'
import { splashStatusMap } from '../windows/splash-window'
import { AuthController } from '../modules/ipc/openapi/auth-controller'
import { TabController } from '../modules/ipc/tab-controller'
import { WebSocketController } from '../modules/ipc/web-socket-controller'
import { RPAController } from '../modules/ipc/rpa-controller'
import { appStore } from '../modules/store/app-store'

export class AppAdapter {
  private static instance: AppAdapter

  private constructor() {
    // 1. 立即执行基础配置
    this.preConfiguration()
    this.watchEarlyEvents()
  }

  public static getInstance(): AppAdapter {
    if (!AppAdapter.instance) {
      AppAdapter.instance = new AppAdapter()
    }
    return AppAdapter.instance
  }

  public init(): void {
    this.setupProtocol() // 注册协议
    this.handleSingleInstance() // 处理单实例和 Windows 唤起
    this.setupProcessHandlers() // 异常处理
    this.watchLifecycleEvents()

    app.whenReady().then(async () => {
      // 在这里“激活”这两个单例
      await appStore.init() // 填充内部的 Store 实例
      await globalState.init() // 读取 Store 并生成初始 State

      await this.setupComponents()
    })
  }

  private async setupComponents(): Promise<void> {
    electronApp.setAppUserModelId('if.xunda.desktop')
    Menu.setApplicationMenu(null)

    IPCManager.register(new LoggerController())
    IPCManager.register(new GlobalStateController())
    IPCManager.register(new AppController())
    IPCManager.register(MonitorController.getInstance())
    IPCManager.register(new TabController())
    IPCManager.register(new WebSocketController())
    IPCManager.register(new TkShopController())
    IPCManager.register(new AuthController())
    IPCManager.register(new RPAController())
    IPCManager.bootstrap()

    await appWindowsAndViewsManager.splashWindow.initWindow()
    appWindowsAndViewsManager.splashWindow.updateProgress(splashStatusMap.INIT_APP)

    //AppDock.getInstance().setup()
    AppTray.getInstance().setup()

    appWindowsAndViewsManager.splashWindow.updateProgress(splashStatusMap.LOAD_CORE_MODULES)

    //TODO: 检测更新

    await appWindowsAndViewsManager.initMainWindow()
    appWindowsAndViewsManager.splashWindow.updateProgress(splashStatusMap.PREPARE_UI)

    app.on('activate', async function () {
      // On macOS it's common to re-create a window in the app when the
      // dock icon is clicked and there are no other windows open.
      if (BrowserWindow.getAllWindows().length === 0) {
        await appWindowsAndViewsManager.initMainWindow()
      } else {
        appWindowsAndViewsManager.mainWindow.showWindow()
        app.dock?.show()
      }
    })

    appWindowsAndViewsManager.splashWindow.updateProgress(splashStatusMap.COMPLETE_STARTUP)
    //await new Promise((resolve) => setTimeout(resolve, 3000))

    setTimeout(() => {
      appWindowsAndViewsManager.splashWindow.closeWindow()
      appWindowsAndViewsManager.mainWindow.showWindow()
    }, 1000)
  }

  /**
   * 只有必须最快监听的事件（如 open-url）
   */
  private watchEarlyEvents(): void {
    if (process.platform === 'darwin') {
      // macOS 建议在这里尽早监听，防止错失启动时的 URL
      app.on('open-url', (event, url) => {
        event.preventDefault()
        this.handleProtocolAction(url)
      })
    }
  }

  /**
   * 通用生命周期（window-all-closed, before-quit）
   */
  private watchLifecycleEvents(): void {
    // 当点击 Dock 菜单的“退出”或按下 Cmd+Q 时触发
    app.on('before-quit', () => {
      globalState.currentState.isQuitting = true
    })

    app.on('window-all-closed', () => {
      if (process.platform !== 'darwin') {
        app.quit()
      }
    })

    app.on('browser-window-created', (_, window) => {
      logger.info(`检测到新窗口创建: ID=${window.id}`)

      // 示例：禁用所有新窗口的默认菜单（常用于生产环境）
      if (import.meta.env.MODE === 'pro') {
        window.setMenu(null)
      }

      // 示例：当窗口被创建时，统一注入某些逻辑或监听常用事件
      window.on('unresponsive', () => {
        logger.warn('检测到窗口卡死，准备重启窗口')
      })

      if (import.meta.env.MODE !== 'pro') {
        window.webContents.debugger.attach()
        window.webContents.debugger.on('message', (_event, method, params) => {
          if (method === 'Network.requestWillBeSent') {
            logger.info('Request:', params.request.url)
          }
          if (method === 'Network.responseReceived') {
            logger.info('Response:', params.response.url, params.response.status)
          }
        })
      }
    })
  }

  /**
   * 1. 注册协议
   */
  private setupProtocol(): void {
    // 开发环境下，如果是 Windows，需要特殊处理环境变量
    if (process.defaultApp) {
      if (process.argv.length >= 2) {
        app.setAsDefaultProtocolClient(AppConfig.APP_PROTOCOL, process.execPath, [path.resolve(process.argv[1])])
      }
    } else {
      app.setAsDefaultProtocolClient(AppConfig.APP_PROTOCOL)
    }
  }

  /**
   * 2. 处理单实例锁 (包含 Windows 唤起逻辑)
   */
  private handleSingleInstance(): void {
    const gotLock = app.requestSingleInstanceLock()
    if (!gotLock) {
      app.quit()
    } else {
      app.on('second-instance', (_event, argv) => {
        // Windows 下从 argv 中提取 URL
        if (process.platform !== 'darwin') {
          const url = argv.find((arg) => arg.startsWith(`${AppConfig.APP_PROTOCOL}://`))
          if (url) this.handleProtocolAction(url)
        }

        // 当尝试启动第二个实例时触发此事件
        if (appWindowsAndViewsManager.mainWindow.baseWindow && !globalState.currentState.isUpdating) {
          if (appWindowsAndViewsManager.mainWindow.baseWindow.isMinimized()) {
            //logger.info('窗口已最小化，恢复窗口')
            appWindowsAndViewsManager.mainWindow.baseWindow.restore()
          }
          if (!appWindowsAndViewsManager.mainWindow.baseWindow.isVisible()) {
            //logger.info('窗口已隐藏，显示窗口')
            appWindowsAndViewsManager.mainWindow.baseWindow.show()
          }
          appWindowsAndViewsManager.mainWindow.baseWindow.focus()
        }
      })
    }
  }

  /**
   * 3. 统一解析 URL 逻辑
   */
  private handleProtocolAction(urlStr: string): void {
    try {
      logger.info(`收到协议请求: ${urlStr}`)
      const url = new URL(urlStr)

      if (!url.protocol.startsWith(AppConfig.APP_PROTOCOL)) return

      if (url.host === 'login' && url.searchParams) {
        const tokenName = url.searchParams.get('tokenName')
        const tokenValue = url.searchParams.get('tokenValue')
        if (tokenName && tokenValue) {
          logger.info(`官网登录: ${tokenName} ${tokenValue}`)
          //TODO: 登录官网
          //appWindowsAndViewsManager.mainWindow?.baseWindow!.webContents.send(IPCChannel.RENDERER_MONITOR_APP_GOOGLE_LOGIN, tokenName, tokenValue)
        }
      }
    } catch (error) {
      logger.error('协议解析失败:', error)
    }
  }

  private setupProcessHandlers(): void {
    process.on('unhandledRejection', (reason) => logger.error('Unhandled Rejection:', reason))
    process.on('uncaughtException', (error) => logger.error('Uncaught Exception:', error))
  }

  /**
   * 应用启动前的硬核配置
   * 必须在 app.ready 之前，甚至在单实例锁之前执行
   */
  private preConfiguration(): void {
    // 禁用叠加滚动条
    app.commandLine.appendSwitch('disable-features', 'OverlayScrollbar')

    // 禁止调试参数
    const forbiddenArgs = ['--remote-debugging-port']
    if (process.argv.some((arg) => forbiddenArgs.includes(arg))) {
      logger.warn('禁止调试参数：' + forbiddenArgs.join(', '))
      app.exit(1)
    }

    // 处理用户数据路径 (区分开发/生产环境)
    const isProd = AppConfig.IS_PRO
    const baseName = 'xunda'
    const folderName = isProd ? baseName : `${baseName}${import.meta.env.MODE}`

    const userDataPath = path.join(app.getPath('appData'), folderName)
    app.setPath('userData', userDataPath)
    initializeLogger()

    // 非生产环境下忽略证书错误
    if (!isProd) {
      app.commandLine.appendSwitch('ignore-certificate-errors')
    }

    logger.info(`程序启动 | 环境: ${import.meta.env.MODE} | UserData: ${userDataPath}`)
  }
}
