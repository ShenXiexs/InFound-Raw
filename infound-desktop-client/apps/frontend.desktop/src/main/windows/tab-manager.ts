// todo: Tab管理通用类，暂时放这，看后续重构
// 合并思路：基于现有的tk-tab-item-manager，合并，尽可能不影响
// 暂定功能:
// 1.通用标签页管理器，不依赖任何业务模块
// 2.负责 WebContentsView 的创建、切换、关闭、导航、状态通知等
// 3.提供的标签页生命周期管理，与 UI 层通过 IPC 通信
import { BrowserWindow, dialog, Menu, MenuItemConstructorOptions, Rectangle, WebContentsView } from 'electron'
import * as path from 'path'
import { AppConfig } from '@common/app-config'
import { randomUUID } from 'crypto'
import { logger } from '../utils/logger'
import { TAB_MAX_COUNT, TAB_TYPES } from '@common/app-constants'
import { MonitorController } from '../modules/ipc/monitor-controller'
import { getFilePath } from '../utils/path-helper'
import { Tab } from '@common/types/tab-type'

export class TabManager {
  private views: Map<string, WebContentsView> = new Map()
  private tabs: Tab[] = []
  private activeTabId: string | null = null
  private readonly tabBarHeight = 40 // 必须与 CSS 中标签栏高度一致
  private readonly addressBarHeight = 44

  constructor(private mainWindow: BrowserWindow) {
    this.setupListeners()
  }

  // 创建新标签页，返回生成的 id，失败返回 null
  public createTab(
    id: string | null = null,
    url: string = 'about:blank',
    type: string = TAB_TYPES.XUNDA,
    options?: {
      insertAfterActive?: boolean
      hideAddress?: boolean
      activate?: boolean
      webPreferences?: Partial<Electron.WebPreferences> // 外部可传入 partition
    }
  ): string | null {
    const { insertAfterActive = true, hideAddress = false, activate = false, webPreferences } = options || {}
    // 检查是否超出tab的最大数，暂定策略，超出后提示用户标签页已达上限；
    // 后期可以根据跟踪标签页的创建时间或最后访问时间，当达到上限时，自动关闭最早创建或最久未访问的标签页
    if (this.tabs.length >= TAB_MAX_COUNT) {
      // 弹出提示对话框（主进程中使用 dialog 模块）
      dialog.showMessageBox(this.mainWindow, {
        type: 'warning',
        title: '标签页数量已达上限',
        message: `最多只能打开 ${TAB_MAX_COUNT} 个标签页。请关闭一些标签页后再试。`,
        buttons: ['确定']
      })

      return null // 返回null表示创建失败
    }

    const newId = id == null ? randomUUID() : id

    logger.info('创建tab:' + newId + ':' + url)

    // 基础配置，与外部传入的合并
    const baseWebPreferences: Electron.WebPreferences = {
      nodeIntegration: false,
      contextIsolation: true, // 强制开启，防止网页 JS 访问主进程模块
      sandbox: true, // 开启沙盒，这是防止调用系统底层 Shell 的最强防线
      webSecurity: true,
      allowRunningInsecureContent: false,
      plugins: false, // 严禁插件，防止插件触发系统调用
      webviewTag: false, // 禁用 webview 标签
      safeDialogs: true,
      devTools: !AppConfig.IS_PRO,
      preload: path.join(getFilePath(), '../renderer/preload.js'),
      ...webPreferences // 合并外部传入（如 partition）
    }

    const view = new WebContentsView({ webPreferences: baseWebPreferences })

    // view.setVisible(false)
    view.webContents.setUserAgent(AppConfig.USER_AGENT)

    // 监听页面标题更新
    view.webContents.on('page-title-updated', (_, title) => {
      const tab = this.tabs.find((t) => t.id === newId)
      if (tab) {
        tab.title = title
        this.sendTabsToRenderer()
      }
    })

    // 监听并接管新窗口地址，新建tab页打开监听到的url
    view.webContents.setWindowOpenHandler((details) => {
      const currentTab = this.tabs.find((t) => t.id === newId)
      const inheritHideAddress = currentTab ? currentTab.hideAddress : false
      this.createTab(null, details.url, type, {
        insertAfterActive: true,
        activate: true,
        hideAddress: inheritHideAddress
        //webPreferences: {} // 不传入 partition，保持默认
      })

      return { action: 'deny' }
    })

    // 监听导航完成事件
    view.webContents.on('did-navigate', (_, url, httpResponseCode, httpStatusText) => {
      //todo:暂时记录
      logger.info(url, httpResponseCode, httpStatusText)

      const tab = this.tabs.find((t) => t.id === newId)
      if (tab) {
        tab.url = url // 更新 URL
        // 标题可能未更新，但 URL 变了，发送更新让渲染进程刷新地址栏
        this.sendTabsToRenderer()
        this.sendNavigationState()
      }
    })

    // 监听页面内导航（如 History API pushState）
    view.webContents.on('did-navigate-in-page', (_, url, isMainFrame) => {
      if (isMainFrame) {
        const tab = this.tabs.find((t) => t.id === newId)
        if (tab) {
          tab.url = url
          this.sendTabsToRenderer()
          this.sendNavigationState()
        }
      }
    })
    //监听当前页的图标，若有变动，重绘【多时可能影响性能，前期影响小】
    view.webContents.on('page-favicon-updated', (_, favicons) => {
      const tab = this.tabs.find((t) => t.id === newId)
      if (tab && favicons.length > 0) {
        tab.favicon = favicons[0]
        this.sendTabsToRenderer()
      }
    })

    // 加载 URL
    view.webContents.loadURL(url)

    // 保存视图和标签信息（但不添加到窗口）
    this.views.set(newId, view)

    const currentTime = Date.now()
    const tab: Tab = {
      id: newId,
      url,
      type,
      title: '新标签页',
      lastAccessed: currentTime,
      createdAt: currentTime,
      hideAddress //：options?.hideAddress
    }

    // 确定插入位置
    let insertIndex = this.tabs.length // 默认末尾
    if (insertAfterActive && this.activeTabId) {
      const activeIndex = this.tabs.findIndex((t) => t.id === this.activeTabId)
      if (activeIndex !== -1) {
        insertIndex = activeIndex + 1
      }
    }

    this.tabs.splice(insertIndex, 0, tab)

    // 如果这是第一个标签，激活，或者指定
    if (this.tabs.length === 1 || activate) {
      this.activateTab(newId)
    }

    this.sendTabsToRenderer()
    return id
  }

  // 激活指定标签页
  public activateTab(id: string): void {
    // for testing logger.info(`TabManager.activateTab called with id=${id}`)
    this.views.forEach((view, vid) => {
      logger.info(`View ${vid} bounds:`, view.getBounds())
    })

    if (this.activeTabId === id || !this.views.has(id)) return
    // logger.info(`TabManager.activateTab called with id=${id}`)
    // 从窗口中移除当前激活的视图（如果有）
    if (this.activeTabId) {
      const oldView = this.views.get(this.activeTabId)
      if (oldView) {
        this.mainWindow.contentView.removeChildView(oldView)
      }
    }

    // 添加新视图到窗口并设置边界
    const newView = this.views.get(id)!
    newView.setBounds(this.getContentBounds())
    this.mainWindow.contentView.addChildView(newView)
    // newView.webContents.focus()
    this.activeTabId = id

    try {
      this.sendTabsToRenderer()
      this.sendNavigationState()

      //激活的tab标签页设置最新的访问时间戳
      const tab = this.tabs.find((t) => t.id === id)
      if (tab) {
        tab.lastAccessed = Date.now()
      }
    } catch (e) {
      //通用错误处理，todo...
    }
  }

  // 关闭指定标签页
  public closeTab(id: string, notReservedOne: boolean = false): boolean {
    if (!this.views.has(id)) return false

    if (!notReservedOne && this.tabs.length === 1) {
      // 可以提示用户，或者直接返回
      dialog.showMessageBox(this.mainWindow, {
        type: 'info',
        title: '提示',
        message: '至少保留一个标签页，无法关闭。'
      })
      return false
    }

    const index = this.tabs.findIndex((t) => t.id === id)
    if (index === -1) return false

    const view = this.views.get(id)!

    if (this.activeTabId === id) {
      this.mainWindow.contentView.removeChildView(view)
      this.activeTabId = null
    }

    // 【下面操作重要：清除内容、释放内存、移除监控，须触发webContent自己的事件，如还在播放的流文件、执行中的脚本等】
    if (!view.webContents.isDestroyed()) {
      //尝试正常关闭 (会触发 beforeunload、unload)
      view.webContents.close()
      //确保资源被释放
      const contents = view.webContents as any
      contents.destroy()
    }

    // 【注意】在创建增加多少个监听，关闭时就移除相应的监听
    view.webContents.removeAllListeners('page-title-updated')
    view.webContents.removeAllListeners('did-navigate')
    view.webContents.removeAllListeners('did-navigate-in-page')
    view.webContents.removeAllListeners('page-favicon-updated')

    this.views.delete(id)
    this.tabs.splice(index, 1)

    if (this.tabs.length > 0) {
      const newIndex = Math.min(index, this.tabs.length - 1)
      this.activateTab(this.tabs[newIndex].id)
    } else {
      //this.createTab() 已有检查必须要保留1个tab，注释掉
    }

    this.sendTabsToRenderer()

    return true
  }

  public goBack(): void {
    const currentView = this.getCurrentView()
    if (currentView && currentView.webContents.navigationHistory.canGoBack()) {
      currentView.webContents.navigationHistory.goBack()
    }
  }

  public goForward(): void {
    const currentView = this.getCurrentView()
    if (currentView && currentView.webContents.navigationHistory.canGoForward()) {
      currentView.webContents.navigationHistory.goForward()
    }
  }

  public reload(): void {
    const currentView = this.getCurrentView()
    if (currentView) {
      currentView.webContents.reload()
    }
  }

  public navigateTo(url: string): void {
    const view = this.getCurrentView()
    if (view) {
      view.webContents.loadURL(url)
      // 可选：更新标签的url属性
      const tab = this.tabs.find((t) => t.id === this.activeTabId)
      if (tab) {
        tab.url = url
        // 如果页面加载后标题更新，会通过page-title-updated事件更新标题，但url可能未更新，这里手动更新url并发送更新通知
        this.sendTabsToRenderer()
      }
    }
  }

  public reorderTabs(orderedIds: string[]): void {
    const newTabs: Tab[] = []
    orderedIds.forEach((id) => {
      const tab = this.tabs.find((t) => t.id === id)
      if (tab) newTabs.push(tab)
    })
    // 将不在 orderedIds 中的标签追加到末尾（防止丢失）
    this.tabs.forEach((tab) => {
      if (!orderedIds.includes(tab.id)) newTabs.push(tab)
    })
    this.tabs = newTabs
    this.sendTabsToRenderer()
  }

  public getTabs(): Tab[] {
    return [...this.tabs]
  }

  public getActiveTabId(): string | null {
    return this.activeTabId
  }

  public getView(id: string): WebContentsView | undefined {
    return this.views.get(id)
  }

  public showTabsMenu(x: number, y: number): void {
    const menuTemplate: MenuItemConstructorOptions[] = this.tabs.map((tab) => ({
      label: tab.title.length > 30 ? tab.title.substring(0, 30) + '…' : tab.title,
      type: 'checkbox',
      checked: tab.id === this.activeTabId,
      click: () => this.activateTab(tab.id)
    }))
    const menu = Menu.buildFromTemplate(menuTemplate)
    menu.popup({
      window: this.mainWindow,
      x: Math.round(x),
      y: Math.round(y)
    })
  }

  // 监听窗口大小变化，更新当前激活视图的边界
  private setupListeners(): void {
    this.mainWindow.on('resize', () => {
      if (this.activeTabId) {
        const view = this.views.get(this.activeTabId)
        if (view) {
          view.setBounds(this.getContentBounds())
        }
      }
    })
  }

  // 计算内容区域（排除标签栏）
  private getContentBounds(): Rectangle {
    const [width, height] = this.mainWindow.getContentSize()
    return {
      x: 0,
      y: this.tabBarHeight + this.addressBarHeight,
      width,
      height: height - this.tabBarHeight - this.addressBarHeight
    }
  }

  private sendNavigationState(): void {
    if (!this.activeTabId) return
    const view = this.views.get(this.activeTabId)
    if (!view) return
    const canGoBack = view.webContents.navigationHistory.canGoBack()
    const canGoForward = view.webContents.navigationHistory.canGoForward()

    MonitorController.getInstance().syncTabsNavigationState(this.mainWindow.webContents, { canGoBack, canGoForward })
  }

  // 获取当前激活的 WebContentsView（供内部和可能的 IPC 使用）
  private getCurrentView(): WebContentsView | null {
    if (!this.activeTabId) return null
    return this.views.get(this.activeTabId) || null
  }

  // 通过 IPC 向渲染进程发送最新标签列表
  private sendTabsToRenderer(): void {
    MonitorController.getInstance().syncTabsUpdated(this.mainWindow.webContents, { activeId: this.activeTabId!, tabs: this.tabs })
  }
}
