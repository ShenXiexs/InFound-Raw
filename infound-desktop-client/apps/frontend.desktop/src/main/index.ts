import path from 'path'
import { app, BrowserWindow, Menu } from 'electron'
import { electronApp, optimizer } from '@electron-toolkit/utils'
import { IPCManager } from './modules/ipc/base/ipc-manager'
import { appWindowsAndViewsManager } from './windows/app-windows-and-views-manager'
import { logger } from './utils/logger'
import { LoggerController } from './modules/ipc/logger-controller'
import { AppController } from './modules/ipc/app-controller'
import { GlobalStateController } from './modules/ipc/global-state-controller'
import { splashStatusMap } from './windows/splash-window'
import { TkShopController } from './modules/ipc/tk-shop-controller'
import { AuthController } from './modules/ipc/auth-controller'
import { MonitorController } from './modules/ipc/monitor-controller'

let userDataPath = path.join(app.getPath('appData'), app.getName())
if (import.meta.env.MODE !== 'pro') {
  userDataPath = path.join(app.getPath('appData'), app.getName() + import.meta.env.MODE)
  app.commandLine.appendSwitch('ignore-certificate-errors')
}
app.setPath('userData', userDataPath)

logger.info('程序启动')

app.whenReady().then(async () => {
  electronApp.setAppUserModelId('if.xunda.rpa.simulation')

  Menu.setApplicationMenu(null)

  // Default open or close DevTools by F12 in development
  // and ignore CommandOrControl + R in production.
  // see https://github.com/alex8088/electron-toolkit/tree/master/packages/utils
  app.on('browser-window-created', (_, window) => {
    optimizer.watchWindowShortcuts(window)
  })

  IPCManager.register(new LoggerController())
  IPCManager.register(new GlobalStateController())
  IPCManager.register(MonitorController.getInstance())
  IPCManager.register(new AppController())
  IPCManager.register(new TkShopController())
  IPCManager.register(new AuthController())
  IPCManager.bootstrap()

  await appWindowsAndViewsManager.splashWindow.initWindow()

  // 模拟阻塞
  //await new Promise((resolve) => setTimeout(resolve, 3000))

  appWindowsAndViewsManager.splashWindow.updateProgress(splashStatusMap.INIT_APP)

  // 模拟阻塞
  await new Promise((resolve) => setTimeout(resolve, 3000))
  appWindowsAndViewsManager.splashWindow.updateProgress(splashStatusMap.LOAD_CORE_MODULES)

  await appWindowsAndViewsManager.initMainWindow()

  // 模拟阻塞
  await new Promise((resolve) => setTimeout(resolve, 3000))
  appWindowsAndViewsManager.splashWindow.updateProgress(splashStatusMap.PREPARE_UI)

  app.on('activate', async function () {
    // On macOS it's common to re-create a window in the app when the
    // dock icon is clicked and there are no other windows open.
    if (BrowserWindow.getAllWindows().length === 0) await appWindowsAndViewsManager.initMainWindow()
  })

  appWindowsAndViewsManager.splashWindow.updateProgress(splashStatusMap.COMPLETE_STARTUP)

  appWindowsAndViewsManager.mainWindow.showWindow()

  appWindowsAndViewsManager.splashWindow.closeWindow()
})

app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})
