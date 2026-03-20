import { randomUUID } from 'crypto'
import path from 'path'
import { BrowserWindow, session, WebContentsView } from 'electron'
import { PageLoadStatus, TkShopSetting, TkShopTabItemSetting, TkShopTabItemView } from '@common/types/tk-type'
import { logger } from '../utils/logger'
import { globalState } from '../modules/state/global-state'
import { AppConfig } from '@common/app-config'
import { AppState } from '@infound/desktop-shared'
import { resetWCVSize, resetWCVSizeToZero } from '../utils/mcv-helper'
import { TransitionWcv } from './transition-wcv'
import { appStore } from '../modules/store/app-store'
import { MonitorController } from '../modules/ipc/monitor-controller'

export class TkTabItemManager {
  private readonly baseWindow: BrowserWindow
  private shopSetting: TkShopSetting
  private tabItemSettings: Record<string, TkShopTabItemSetting>
  private tabItemViews: Record<string, TkShopTabItemView>
  private currentTabItemId: string
  private currentTabItemView: TkShopTabItemView | null
  private currentState: AppState = globalState.currentState
  private transitionWcv: TransitionWcv

  constructor(baseWindow: BrowserWindow, shopSetting: TkShopSetting) {
    this.baseWindow = baseWindow
    this.shopSetting = shopSetting
    this.tabItemSettings = {}
    this.tabItemViews = {}
    this.currentTabItemId = ''
    this.currentTabItemView = null
    this.transitionWcv = new TransitionWcv(baseWindow)
  }

  public async initTabViews(): Promise<void> {
    if (!globalState.currentState.isLogin) {
      return Promise.resolve()
    }

    logger.info('初始化 TK 店铺 Tab 视图')
    this.tabItemSettings = this.getTabItemSettingsFromStorage()
    MonitorController.getInstance().syncTkShopAllTabItemSettings(this.baseWindow.webContents, this.tabItemSettings)

    await this.transitionWcv.initView()

    let focusedTabItemId = Object.keys(this.tabItemSettings).find((id) => this.tabItemSettings[id].focused)
    if (!focusedTabItemId) focusedTabItemId = Object.keys(this.tabItemSettings)[0]

    const focusedTabItemSetting = this.tabItemSettings[focusedTabItemId]
    if (focusedTabItemSetting) {
      const tabItemView = await this.createTabItemView(focusedTabItemSetting)
      this.currentTabItemId = focusedTabItemSetting.id
      this.currentTabItemView = tabItemView
      this.showTabItemView(focusedTabItemSetting.id)
    }

    // 优化其他标签页的加载策略
    await this.scheduleBackgroundTabLoading(focusedTabItemId)
  }

  public showTabItemView(id: string): void {
    if (this.currentTabItemId === id && this.currentTabItemView != null) {
      const viteBounds = this.currentTabItemView.webContentsView.getBounds()
      if (!(viteBounds.height > 0)) {
        this.baseWindow!.contentView.addChildView(this.currentTabItemView.webContentsView)
        resetWCVSize(this.baseWindow!, this.currentTabItemView.webContentsView)
        if (this.currentTabItemView.pageLoadStatus === PageLoadStatus.TargetPage) {
          this.transitionWcv.displayTransitionLoadingWCV()
        } else {
          this.transitionWcv.showTransitionLoadingWCV()
          this.transitionWcv.openTransitionWCV({
            routerPath: this.currentTabItemView.pageLoadStatus === PageLoadStatus.Loading ? '/loading' : '/error'
          })
        }
      }
      this.currentTabItemView.webContentsView.webContents?.setFrameRate(60) // 高帧率
    } else {
      if (this.currentTabItemView != null) {
        resetWCVSizeToZero(this.currentTabItemView.webContentsView)
        this.currentTabItemView.webContentsView.webContents?.setFrameRate(1) // 低帧率
      }
      const tabItemView = this.tabItemViews[id]
      if (tabItemView != null) {
        //logger.info(`showTabItemView: ${id}`)
        const view = tabItemView.webContentsView
        resetWCVSize(this.baseWindow!, view)
        this.currentTabItemId = id
        this.currentTabItemView = tabItemView
        this.baseWindow!.contentView.addChildView(view)
        if (tabItemView.pageLoadStatus === PageLoadStatus.TargetPage) {
          this.transitionWcv.displayTransitionLoadingWCV()
        } else {
          this.transitionWcv.showTransitionLoadingWCV()
          this.transitionWcv.openTransitionWCV({
            routerPath: this.currentTabItemView?.pageLoadStatus === PageLoadStatus.Loading ? '/loading' : '/error'
          })
        }
      }
    }
  }

  public resizeTabItemView(): void {
    if (this.currentTabItemView != null && this.currentTabItemView.webContentsView.getBounds().width > 0) {
      resetWCVSize(this.baseWindow!, this.currentTabItemView.webContentsView)
    }

    if (this.transitionWcv.isShowing()) {
      this.transitionWcv.showTransitionLoadingWCV()
    }
  }

  private async scheduleBackgroundTabLoading(excludedId: string): Promise<void> {
    const maxTabs = globalState.currentState.currentUser?.maxShopsCount ?? 5
    let loadIndex = 0
    const tabItemSettings = Object.values(this.tabItemSettings)
    const loadNextTab = async (): Promise<void> => {
      const tabItemSetting = tabItemSettings[loadIndex++]
      if (tabItemSetting == null || tabItemSetting.id == excludedId || !tabItemSetting.enabled || loadIndex >= maxTabs) return

      if (this.tabItemViews[tabItemSetting.id] == null) {
        await this.createTabItemView(tabItemSetting)

        // 递归调度下一个加载（带随机延迟）
        const delay = 800 + Math.random() * 800 // 3-5秒随机延迟
        setTimeout(loadNextTab, delay)
      } else {
        await loadNextTab() // 如果已存在则跳过
      }
    }

    // 使用空闲回调启动后台加载
    if (typeof requestIdleCallback === 'function') {
      requestIdleCallback(async () => {
        setTimeout(loadNextTab, 500) // 等待主标签加载完成
      })
    } else {
      setTimeout(loadNextTab, 800) // 兼容方案
    }
  }

  private getTabItemSettingsFromStorage(): Record<string, TkShopTabItemSetting> {
    let tabItemSettings: Record<string, TkShopTabItemSetting> | null =
      globalState.currentState.currentUser == null ? null : appStore.get(`tkShops.${globalState.currentState.currentUser!.userId}`)

    if (tabItemSettings == null) {
      tabItemSettings = {}
      const key = 'xd-' + randomUUID()
      tabItemSettings[key] = {
        id: key,
        type: 'tk',
        name: 'TK 店铺 A',
        url: this.shopSetting.loginUrl,
        icon: '',
        focused: true,
        enabled: true
      } as TkShopTabItemSetting
    } else {
      // 删除超出 maxTabs 的项
      const entries = Object.entries(tabItemSettings)
      let index = 0
      entries.forEach(([_key, setting]) => {
        setting.enabled = index < globalState.currentState.currentUser!.maxShopsCount
        index++
      })
    }
    this.saveToStorage(tabItemSettings)
    return tabItemSettings
  }

  private saveToStorage(tabItemSettings: Record<string, TkShopTabItemSetting>): void {
    appStore.set(`tkShops.${globalState.currentState.currentUser?.userId}`, tabItemSettings)
  }

  private async createTabItemView(tabItemSetting: TkShopTabItemSetting): Promise<TkShopTabItemView | null> {
    const persistKey = 'persist:' + this.currentState.currentUser?.userId + ':' + this.shopSetting.id
    const sess = session.fromPartition(persistKey)

    const wcv: WebContentsView = new WebContentsView({
      webPreferences: {
        partition: persistKey,
        preload: path.join(__dirname, '../preload/index.cjs'),
        session: sess,
        devTools: !AppConfig.IS_PRO,
        contextIsolation: true, // 强制开启，防止网页 JS 访问主进程模块
        nodeIntegration: false, // 严禁 Node.js 环境
        sandbox: true, // 开启沙盒，这是防止调用系统底层 Shell 的最强防线
        safeDialogs: true,
        webSecurity: true,
        allowRunningInsecureContent: false,
        plugins: false, // 严禁插件，防止插件触发系统调用
        webviewTag: false // 禁用 webview 标签
      }
    })

    wcv.setVisible(false)
    wcv.webContents.setUserAgent(AppConfig.USER_AGENT)

    //monitorNavigation(logger, wcv.webContents)

    const tabItemView: TkShopTabItemView = {
      targetUrl: tabItemSetting.url,
      webContentsView: wcv,
      pageLoadStatus: PageLoadStatus.Loading
    }

    ;(wcv.webContents as any).on('will-frame-navigate', (event: Electron.Event, url: string) => {
      if (!url.startsWith('http') && !url.startsWith('https')) {
        logger.warn(`拦截到子框架的协议跳转: ${url}`)
        event.preventDefault() // 这一步在子框架中同样有效
      }
      /*if (isMainFrame) {
        tabItemView.pageLoadStatus = PageLoadStatus.Loading
        if (!this.transitionWcv.isShowing()) {
          this.transitionWcv.showTransitionLoadingWCV()
        }
      }*/
    })

    /*wcv.webContents.on('render-process-gone', (_event: Electron.Event, details: Electron.RenderProcessGoneDetails) => {
      const { reason } = details
      logger.error(`渲染进程崩溃: ${reason === 'killed' ? '被杀死' : '意外崩溃'}`)
      logger.error(`崩溃页面: ${wcv.webContents.getURL()}`)
    })

    // 监听渲染进程无响应
    wcv.webContents.on('unresponsive', () => {
      logger.error('渲染进程无响应')
    })*/

    wcv.webContents.on('dom-ready', () => {
      if (tabItemView.pageLoadStatus == PageLoadStatus.Loading && this.currentTabItemId === tabItemSetting.id) {
        logger.info('关闭 transitionWCV')
        this.transitionWcv.displayTransitionLoadingWCV()
      }
    })

    wcv.webContents.on('did-frame-finish-load', (_event, isMainFrame): void => {
      if (tabItemView.pageLoadStatus == PageLoadStatus.ErrorPage) return
      if (isMainFrame) {
        logger.info('页面加载完成')
        tabItemView.pageLoadStatus = PageLoadStatus.TargetPage
      }
    })

    wcv.webContents.on('did-fail-provisional-load', () => {
      tabItemView.pageLoadStatus = PageLoadStatus.ErrorPage
      if (this.currentTabItemId === tabItemSetting.id) {
        this.transitionWcv.openTransitionWCV({
          routerPath: '/error'
        })
      }
    })

    await wcv.webContents.loadURL(tabItemSetting.url)

    this.tabItemViews[tabItemSetting.id] = tabItemView

    return tabItemView
  }
}
