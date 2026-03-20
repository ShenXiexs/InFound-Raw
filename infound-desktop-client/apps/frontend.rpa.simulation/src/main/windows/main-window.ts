import { app, BrowserWindow, screen, shell } from 'electron'
import { join } from 'path'
import icon from '../../../resources/icon.png?asset'
import { is } from '@electron-toolkit/utils'
import { AppConfig } from '@common/app-config'
import { appWindowsAndViewsManager } from './app-windows-and-views-manager'

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
      width: width,
      height: height,
      minHeight: 300,
      minWidth: 600,
      ...(process.platform === 'linux' ? { icon } : {}),
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
        preload: join(__dirname, '../preload/index.js'),
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
      appWindowsAndViewsManager.resize()
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
      await this.baseWindow.loadFile(join(__dirname, '../renderer/index.html'))
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
