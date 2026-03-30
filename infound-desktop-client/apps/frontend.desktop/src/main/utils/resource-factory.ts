import { nativeImage, NativeImage } from 'electron'
import * as path from 'path'
import { globalState } from '../modules/state/global-state'
import { logger } from './logger'

export class ResourceFactory {
  /**
   * 专门为 Tray (托盘/状态栏) 准备的图标加载器
   */
  static getTrayIcon(): NativeImage {
    const state = globalState.currentState
    const platformFolder = state.isMac ? 'mac' : 'win'
    const fileName = state.isMac ? 'iconTemplate.png' : 'icon.png'

    const iconPath = path.join(globalState.currentState.appSetting.resourcesPath, 'icons', platformFolder, fileName)

    // 创建 NativeImage
    const image = nativeImage.createFromPath(iconPath)

    if (state.isMac) {
      // 核心：在 Mac 上开启模板模式，处理深浅色切换
      // 如果文件名已经叫 xxxTemplate.png，Electron 会自动识别，
      // 但显式调用 setTemplateImage(true) 更稳妥。
      image.setTemplateImage(true)
    }

    if (image.isEmpty()) {
      logger.error(`[ResourceFactory] 无法在路径找到图标: ${iconPath}`)
    }

    return image
  }

  /**
   * 获取通用的 App Logo (用于关于界面或窗口图标)
   */
  static getAppLogo(): NativeImage {
    const logoPath = path.join(globalState.currentState.appSetting.resourcesPath, 'icons', 'common', 'logo.png')
    return nativeImage.createFromPath(logoPath)
  }
}
