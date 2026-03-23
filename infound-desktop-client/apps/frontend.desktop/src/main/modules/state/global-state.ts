// 客户端临时状态缓存，主进程与渲染进程共用
import path from 'path'
import fs from 'fs'
import { app, webContents } from 'electron'
import pkg from 'node-machine-id'
import { set } from 'radash'
import { AppInfo, AppSetting, AppState, CurrentUserInfo } from '@infound/desktop-shared'
import { logger } from '../../utils/logger'
import { appStore } from '../store/app-store'
import { credentialStore } from '../store/credential-store'
import { AppConfig } from '@common/app-config'
import { MonitorController } from '../ipc/monitor-controller'
import { getFilePath } from '../../utils/path-helper'

const { machineIdSync } = pkg

class GlobalState {
  private state: AppState

  constructor() {
    const userInfo = this.getCurrentUser()
    const userEnableDebug = userInfo?.enableDebug ?? userInfo?.permission?.enableDebug ?? false
    this.state = {
      appInfo: this.getAppInfo(),
      appSetting: this.getAppSetting(),
      isUpdating: false,
      isLogin: AppConfig.IS_PRO ? userInfo != null && userInfo.userId !== '' : true,
      enableDebug: userEnableDebug,
      currentUser: userInfo
    } as AppState
  }

  public get currentState(): AppState {
    return this.state
  }

  public async saveState(path: string, value: any): Promise<void> {
    // 1. 更新内存状态 (确保主进程内逻辑拿到的始终是最新的)
    this.state = set(this.state, path, value)

    // 2. 持久化分流处理
    if (path.startsWith('currentUser.tokenValue')) {
      // 敏感信息走 CredentialStore
      await credentialStore.saveToken(value)
    } else if (path.startsWith('appSetting') || path.startsWith('currentUser')) {
      // 普通配置信息走 AppStore
      appStore.set(path, value)
    }

    // 3. 广播通知渲染进程同步 Pinia
    this.broadcastToRenderers(path, value)

    logger.info(`State updated: ${path} = ${value}`)
  }

  private broadcastToRenderers(path: string, value: any): void {
    // 1. 构造精简的负载
    const payload = { path, value }

    // 2. 获取所有的 WebContents (包含窗口和独立的 View)
    const allWebContents = webContents.getAllWebContents()

    allWebContents.forEach((wc) => {
      // 过滤掉已经销毁的或正在崩溃的实例
      if (!wc.isDestroyed() && !wc.isCrashed()) {
        MonitorController.getInstance().syncAppGlobalState(wc, payload)
      }
    })
  }

  private getAppInfo(): AppInfo {
    const localDeviceId = appStore.get<string>('deviceId', '')?.trim()
    const deviceId = machineIdSync(true).trim()

    // 首次写入，本地已有值则不做迁移覆盖
    if (!localDeviceId) {
      appStore.set('deviceId', deviceId)
      logger.info(`deviceId 已初始化: ${deviceId}`)
    }

    return {
      name: app.getName(),
      version: app.getVersion(),
      description: '',
      deviceId: deviceId,
      sessionId: Date.now()
    } as AppInfo
  }

  private getAppSetting(): AppSetting {
    let resourcesPath: string
    if (app.isPackaged) {
      resourcesPath = path.join(process.resourcesPath)
    } else {
      const candidatePaths = [path.join(app.getAppPath(), 'resources'), path.join(app.getAppPath(), '../resources'), path.join(getFilePath(), '../../resources')]
      const hitPath = candidatePaths.find((item) => fs.existsSync(item))
      resourcesPath = hitPath || candidatePaths[0]
    }
    // 增加文件存在性检查
    if (!fs.existsSync(resourcesPath)) {
      logger.error(`Static file path not found: ${resourcesPath}`)
    } else {
      logger.info(`Static file path resolved: ${resourcesPath}`)
    }

    return {
      resourcesPath: resourcesPath,
      ui: {
        tabItemLeftSize: appStore.get<number>('appSetting.ui.tabItemLeftSize', 210),
        splitSpace: 4
      }
    } as AppSetting
  }

  private getCurrentUser(): CurrentUserInfo | undefined {
    const userInfo = appStore.get<CurrentUserInfo>('currentUser')
    if (userInfo) {
      credentialStore.getToken().then((token) => (userInfo.tokenValue = token || ''))
      return userInfo as CurrentUserInfo
    } else return undefined
  }
}

export const globalState = new GlobalState()
