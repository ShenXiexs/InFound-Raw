import path from 'path'
import { BrowserWindow, shell, type WebContents } from 'electron'
import { AppConfig } from '@common/app-config'
import { buildEmbedPageUrl } from '../services/embed-page-url'
import { getFilePath } from '../utils/path-helper'
import { ResourceFactory } from '../utils/resource-factory'
import { logger } from '../utils/logger'

/** 供 embed 识别模态壳：query + hash 双写（hash 路由下 `location.search` 常为空） */
function appendEmbedModalMarkers(pageUrl: string): string {
  const u = new URL(pageUrl)
  u.searchParams.set('embedModal', '1')

  const hashRaw = u.hash.replace(/^#/, '').trim()
  if (!hashRaw) {
    u.hash = '#/outreach?embedModal=1'
    return u.toString()
  }

  const qIndex = hashRaw.indexOf('?')
  const pathPart = qIndex >= 0 ? hashRaw.slice(0, qIndex) : hashRaw
  const queryPart = qIndex >= 0 ? hashRaw.slice(qIndex + 1) : ''
  const hp = new URLSearchParams(queryPart)
  hp.set('embedModal', '1')
  const q = hp.toString()
  u.hash = `#${pathPart}${q ? `?${q}` : ''}`
  return u.toString()
}

/**
 * 独立 embed 模态窗口（parent + modal），用于设置页等，与店铺窗口分离。
 */
export class EmbedModalWindowManager {
  private embedWindow: BrowserWindow | null = null

  async open(parent: BrowserWindow, hashPath: string): Promise<{ success: boolean; error?: string }> {
    const raw = typeof hashPath === 'string' ? hashPath.trim() : ''
    const normalized = raw.startsWith('/') ? raw : `/${raw || 'settings'}`

    try {
      const url = await buildEmbedPageUrl(normalized)

      if (!this.embedWindow || this.embedWindow.isDestroyed()) {
        this.embedWindow = new BrowserWindow({
          parent,
          modal: true,
          title: '设置',
          width: 800,
          height: 640,
          minWidth: 560,
          minHeight: 400,
          show: false,
          center: true,
          icon: ResourceFactory.getTrayIcon(),
          frame: false,
          autoHideMenuBar: true,
          backgroundColor: '#FFFFFF',
          movable: true,
          maximizable: true,
          minimizable: true,
          resizable: true,
          webPreferences: {
            preload: path.join(getFilePath(), '../preload/index.cjs'),
            webSecurity: false,
            sandbox: false,
            devTools: !AppConfig.IS_PRO,
            partition: 'persist:embed'
          }
        })

        this.embedWindow.webContents.setWindowOpenHandler((details) => {
          shell.openExternal(details.url).then(() => {})
          return { action: 'deny' }
        })

        this.embedWindow.on('closed', () => {
          this.embedWindow = null
        })
      }

      const finalUrl = appendEmbedModalMarkers(url)
      await this.embedWindow.loadURL(finalUrl)
      this.embedWindow.show()
      this.embedWindow.focus()
      return { success: true }
    } catch (error: any) {
      logger.error('[EmbedModal] 打开失败', error)
      return { success: false, error: error?.message || '打开设置失败' }
    }
  }

  /** 由 embed 页内发起关闭（仅关闭本管理器创建的模态窗） */
  closeFromWebContents(sender: WebContents): void {
    const win = BrowserWindow.fromWebContents(sender)
    if (!win || win.isDestroyed()) {
      return
    }
    if (this.embedWindow && !this.embedWindow.isDestroyed() && this.embedWindow.id === win.id) {
      this.embedWindow.close()
    }
  }
}

export const embedModalWindowManager = new EmbedModalWindowManager()
