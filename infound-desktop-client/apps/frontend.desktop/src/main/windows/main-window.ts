import path from 'path'
import { app, BrowserWindow, screen, shell } from 'electron'
import { is } from '@electron-toolkit/utils'
import { AppConfig } from '@common/app-config'
import { appWindowsAndViewsManager } from './app-windows-and-views-manager'
import { globalState } from '../modules/state/global-state'

export class MainWindow {
  public baseWindow: BrowserWindow | null = null

  constructor() {
    this.baseWindow = null
  }

  public async initWindow(): Promise<BrowserWindow> {
    const primaryDisplay = screen.getPrimaryDisplay()
    const { workArea } = primaryDisplay

    const width = 960
    const height = 678
    const x = (workArea.width - width) / 2
    const y = (workArea.height - height) / 2

    // Create the browser window.
    this.baseWindow = new BrowserWindow({
      title: '寻达',
      width: width,
      height: height,
      minHeight: 300,
      minWidth: 600,
      icon: path.join(globalState.currentState.appSetting.resourcesPath, 'icon.png'),
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
        preload: path.join(AppConfig.DIR_NAME, '../preload/index.cjs'),
        webSecurity: false,
        sandbox: false,
        devTools: !AppConfig.IS_PRO,
        partition: 'persist:main'
      }
    })

    this.baseWindow.on('close', (e) => {
      e.preventDefault()
      this.baseWindow?.hide()
    })

    this.baseWindow.on('closed', () => {
      if (process.platform !== 'darwin' && app) {
        app.quit()
      }
    })

    this.baseWindow.on('resize', () => {
      appWindowsAndViewsManager.mainWindowResize()
    })

    this.baseWindow.webContents.setWindowOpenHandler((details) => {
      shell.openExternal(details.url).then(() => {})
      return { action: 'deny' }
    })

    this.baseWindow.setMenuBarVisibility(false)
    this.baseWindow.setMenu(null)

    if (is.dev && process.env['ELECTRON_RENDERER_URL']) {
      await this.baseWindow.loadURL(process.env['ELECTRON_RENDERER_URL'])
    } else {
      await this.baseWindow.loadFile(path.join(AppConfig.DIR_NAME, '../renderer/index.html'))
    }

    if (this.baseWindow.isVisible()) {
      this.baseWindow.focus()
    }

    return this.baseWindow!
  }

  public showWindow(): void {
    if (this.baseWindow) {
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
