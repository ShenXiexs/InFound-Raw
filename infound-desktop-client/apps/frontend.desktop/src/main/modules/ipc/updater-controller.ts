import { app, BrowserWindow } from 'electron'
import electronUpdater from 'electron-updater'
import { IPCGateway, IPCHandle, IPCType } from './base/ipc-decorator'
import { IPC_CHANNELS } from '@common/types/ipc-type'
import { AppReleaseInfo } from '@infound/desktop-base'
import { AppConfig } from '@common/app-config'
import { logger } from '../../utils/logger'
import { MonitorController } from './monitor-controller'
import { globalState } from '../state/global-state'
import { appWindowsAndViewsManager } from '../../windows/app-windows-and-views-manager'

const { autoUpdater } = electronUpdater

export class UpdaterController {
  private static instance: UpdaterController
  private appReleaseInfo: AppReleaseInfo = {
    needUpdate: false,
    version: '',
    releaseDate: '',
    releaseNotes: ''
  }
  private updaterWindowId: number = 0
  private updateType: 'immediately' | 'afterExit' = 'immediately'

  // 1. 私有化构造函数，防止外部 new
  private constructor() {
    // 初始化逻辑
  }

  // 2. 提供获取单例的静态方法
  public static getInstance(): UpdaterController {
    if (!UpdaterController.instance) {
      UpdaterController.instance = new UpdaterController()
      UpdaterController.instance.init()
    }
    return UpdaterController.instance
  }

  @IPCHandle(IPCGateway.APP, IPC_CHANNELS.APP_UPDATE_INFO, IPCType.INVOKE)
  async appUpdateInfo(_event: any): Promise<{ success: boolean; data?: AppReleaseInfo; error?: string }> {
    return {
      success: true,
      data: this.appReleaseInfo!
    }
  }

  @IPCHandle(IPCGateway.APP, IPC_CHANNELS.APP_UPDATE_CHECK, IPCType.INVOKE)
  async appUpdateCheck(_event: any): Promise<{ success: boolean; data?: AppReleaseInfo; error?: string }> {
    try {
      const res = await autoUpdater.checkForUpdatesAndNotify()
      if (res?.isUpdateAvailable) {
        await appWindowsAndViewsManager.updaterWindow.initWindow()
      }
      return {
        success: true,
        data: this.appReleaseInfo!
      }
    } catch (error) {
      return { success: false, error: (error as Error).message }
    }
  }

  @IPCHandle(IPCGateway.APP, IPC_CHANNELS.APP_UPDATE_DOWNLOAD, IPCType.INVOKE)
  async appUpdateDownload(_event: any, mainWindowId: number, updateType: 'immediately' | 'afterExit'): Promise<{ success: boolean; data?: AppReleaseInfo; error?: string }> {
    this.updaterWindowId = mainWindowId
    this.updateType = updateType
    if (this.updateType == 'afterExit') {
      //logger.info('show main window')
      globalState.currentState.isUpdating = false
      appWindowsAndViewsManager.mainWindow.baseWindow!.show()
    } else {
      autoUpdater.autoDownload = true
      await autoUpdater.checkForUpdates()
    }
    return {
      success: true
    }
  }

  @IPCHandle(IPCGateway.APP, IPC_CHANNELS.APP_UPDATE_CLOSE, IPCType.SEND)
  async closeWindow(_event: any): Promise<void> {
    appWindowsAndViewsManager.updaterWindow.closeWindow()
  }

  private init(): void {
    //logger.info('AppUpdaterManager init')
    // 关闭自动更新
    autoUpdater.autoDownload = false
    // 开启开发环境调试，后边会有说明
    if (!AppConfig.IS_PRO) {
      autoUpdater.forceDevUpdateConfig = true
    }
    // 应用退出后自动安装
    autoUpdater.autoInstallOnAppQuit = true

    autoUpdater.logger = logger

    // 监听升级失败事件
    autoUpdater.on('error', (error) => {
      logger.error(`error: ${JSON.stringify(error)}`)
    })

    //监听发现可用更新事件
    autoUpdater.on('update-available', (info) => {
      logger.info(`update-available: ${JSON.stringify(info)}`)
      this.appReleaseInfo = {
        needUpdate: true,
        version: info.version,
        releaseDate: info.releaseDate,
        releaseNotes: info.releaseNotes?.toString() || ''
      }
    })

    //监听没有可用更新事件
    autoUpdater.on('update-not-available', (info) => {
      logger.info(`update-not-available: ${JSON.stringify(info)}`)
      this.appReleaseInfo = {
        needUpdate: false,
        version: info.version,
        releaseDate: info.releaseDate,
        releaseNotes: info.releaseNotes?.toString() || ''
      }
    })

    // 更新下载进度事件
    autoUpdater.on('download-progress', (prog) => {
      const speed = prog.bytesPerSecond / 1000000 > 1 ? Math.ceil(prog.bytesPerSecond / 1000000) + 'M/s' : Math.ceil(prog.bytesPerSecond / 1000) + 'K/s'
      const window = BrowserWindow.fromId(this.updaterWindowId)
      MonitorController.getInstance().syncAppUpdateProgress(window!.webContents, speed, Math.ceil(prog.percent))
    })

    //监听下载完成事件
    autoUpdater.on('update-downloaded', (_releaseObj) => {
      //logger.info(`update-downloaded: ${JSON.stringify(releaseObj)}`)
      //退出并安装更新包
      if (this.updateType === 'immediately') {
        autoUpdater.quitAndInstall()
      } else {
        app.once('before-quit', () => {
          autoUpdater.quitAndInstall(false, true)
        })
      }
    })
  }
}
