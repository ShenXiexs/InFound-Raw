import { app, BrowserWindow, screen, shell } from 'electron'
import path from 'path'
import { AppConfig } from '@common/app-config'
import { is } from '@electron-toolkit/utils'
import { TkShopSetting } from '@common/types/tk-type'
import { TkTabItemManager } from './tk-tab-item-manager'
import { getFilePath } from '../utils/path-helper'
import { ResourceFactory } from '../utils/resource-factory'

export class TkShopWindow {
  public baseWindow: BrowserWindow | null = null
  public tabItemManager: TkTabItemManager | null = null

  public async initWindow(shopSetting: TkShopSetting): Promise<void> {
    const primaryDisplay = screen.getPrimaryDisplay()
    const { workArea } = primaryDisplay

    const width = 960
    const height = 678
    const x = (workArea.width - width) / 2
    const y = (workArea.height - height) / 2

    // Create the browser window.
    this.baseWindow = new BrowserWindow({
      title: shopSetting.name,
      width: width,
      height: height,
      minHeight: 300,
      minWidth: 600,
      icon: ResourceFactory.getTrayIcon(),
      x: x,
      y: y,
      show: false,
      frame: false,
      autoHideMenuBar: true,
      backgroundColor: '#FCFCFC',
      maximizable: true,
      minimizable: true,
      resizable: true,
      webPreferences: {
        preload: path.join(getFilePath(), '../preload/index.cjs'),
        webSecurity: false,
        sandbox: false,
        devTools: !AppConfig.IS_PRO,
        partition: 'persist:main'
      }
    })

    shopSetting.windowId = this.baseWindow.id

    const uniqueAppId = `xunda.shop.${shopSetting.id}`

    if (process.platform === 'win32') {
      this.baseWindow.setAppDetails({
        appId: uniqueAppId
      })
      shopSetting.osWinAppId = uniqueAppId
    }

    //todo: 有关是否真正的关闭？我认为应该真关，如果只是隐藏，正在执行的脚本和流文件依然占据内存，只要保证tab状态持久化，加载也不太影响用户体验
    this.baseWindow.on('close', (e) => {
      e.preventDefault()
      this.tabItemManager!.saveTabItemSettings() //关闭时保存Tab页状态
      this.tabItemManager!.closeTabItems()
      this.baseWindow?.hide()
    })

    this.baseWindow.on('closed', () => {
      if (process.platform !== 'darwin' && app) {
        app.quit()
      }
    })

    this.baseWindow.on('resize', () => {
      this.tabItemManager!.resizeTabItemView()
    })

    this.baseWindow.on('page-title-updated', (e) => e.preventDefault())
    this.baseWindow.webContents.on('page-title-updated', (e) => e.preventDefault())

    this.baseWindow.webContents.setWindowOpenHandler((details) => {
      shell.openExternal(details.url).then(() => {})
      return { action: 'deny' }
    })

    this.baseWindow.setMenuBarVisibility(false)
    this.baseWindow.setMenu(null)

    if (is.dev && process.env['ELECTRON_RENDERER_URL']) {
      await this.baseWindow.loadURL(`${process.env['ELECTRON_RENDERER_URL']}/tkshop.html`)
    } else {
      await this.baseWindow.loadFile(path.join(getFilePath(), '../renderer/tkshop.html'))
    }

    if (this.baseWindow.isVisible()) {
      this.baseWindow.focus()
    }

    this.tabItemManager = new TkTabItemManager(this.baseWindow, shopSetting)
  }

  public showWindow(): void {
    if (this.baseWindow) {
      this.tabItemManager?.initTabViews()
      this.baseWindow.show()
    }
  }

  public closeWindow(): void {
    if (this.baseWindow) {
      this.baseWindow.close()
      this.baseWindow = null!
    }
  }
}
