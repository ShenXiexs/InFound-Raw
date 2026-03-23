import { randomUUID } from 'crypto'
import { BrowserWindow, WebContentsView } from 'electron'
import { PageLoadStatus, TkShopSetting, TkShopTabItemSetting } from '@common/types/tk-type'
import { logger } from '../utils/logger'
import { globalState } from '../modules/state/global-state'
import { AppState, CurrentUserInfo } from '@infound/desktop-shared'
import { resetWCVSize } from '../utils/mcv-helper'
import { TransitionWcv } from './transition-wcv'
import { appStore } from '../modules/store/app-store'
import { TabManager } from './tab-manager'
import { TAB_TYPES } from '@common/app-constants'

export class TkTabItemManager {
  private readonly baseWindow: BrowserWindow
  private currentUser: CurrentUserInfo | null = null
  private shopSetting: TkShopSetting
  private tabItemSettings: Record<string, TkShopTabItemSetting> = {}
  private readonly tabPersistKey: string
  // private readonly backgroundLoadingCount: number
  private currentTabItemId: string | null = null
  private currentState: AppState = globalState.currentState
  private transitionWcv: TransitionWcv
  private readonly tabManager: TabManager
  private businessData: Map<string, { pageLoadStatus: PageLoadStatus; targetUrl: string }> = new Map() // todo:业务数据

  constructor(baseWindow: BrowserWindow, shopSetting: TkShopSetting) {
    this.baseWindow = baseWindow
    this.shopSetting = shopSetting
    this.tabManager = new TabManager(baseWindow)
    ;(baseWindow as any).tabManager = this.tabManager
    ;(baseWindow as any).tkTabItemManager = this
    this.tabPersistKey = `persist:${this.currentState.currentUser?.userId}:${shopSetting.id}`
    this.transitionWcv = new TransitionWcv(baseWindow)
    // this.backgroundLoadingCount = TAB_MAX_COUNT //暂定...
  }

  public async initTabViews(): Promise<void> {
    if (!globalState.currentState.isLogin) {
      return Promise.resolve()
    }

    this.currentUser = globalState.currentState.currentUser!
    this.tabItemSettings = this.loadTabItemSettings()

    //todo: 这句的作用是？不理解，保存...
    //MonitorController.getInstance().syncTkShopAllTabItemSettings(this.baseWindow.webContents, this.tabItemSettings)

    logger.info('初始化 TK 店铺 Tab 视图')
    await this.transitionWcv.initView()

    // 按顺序一次性创建所有标签页（不激活）
    const entries = Object.entries(this.tabItemSettings) // 顺序取决于插入顺序
    let focusedId = ''
    for (const [id, setting] of entries) {
      if (setting.focused) focusedId = setting.id
      // 创建标签页，activate 为 false
      await this.createTabView(id, setting.url, setting.type, false, false)
    }

    if (focusedId) {
      this.showTabItemView(focusedId)
    } else if (entries.length > 0) {
      // 如果没有焦点标签，激活第一个
      this.showTabItemView(entries[0][0])
    }

    // 找出焦点标签
    // let focusedTabItemId = Object.keys(this.tabItemSettings).find((id) => this.tabItemSettings[id].focused)
    // if (!focusedTabItemId) focusedTabItemId = Object.keys(this.tabItemSettings)[0]
    //
    // if (focusedTabItemId) {
    //   const setting = this.tabItemSettings[focusedTabItemId]
    //
    //   // 确保标签页已创建（可能存储中的标签页尚未创建）
    //   if (!this.tabManager.getView(focusedTabItemId)) {
    //     focusedTabItemId = await this.createTabView(focusedTabItemId, setting.url, setting.type, true, true)
    //   }
    //
    //   this.showTabItemView(focusedTabItemId)
    //}

    // 优化其他标签页的加载策略
    //await this.scheduleBackgroundTabLoading(focusedTabItemId)
  }

  public showTabItemView(id: string | undefined): void {
    if (!id || !this.tabManager.getView(id)) return

    // 先隐藏过渡视图（确保不遮挡）
    this.transitionWcv.displayTransitionLoadingWCV()

    this.tabManager.activateTab(id)
    this.currentTabItemId = id

    const biz = this.businessData.get(id)
    if (biz) {
      if (biz.pageLoadStatus === PageLoadStatus.TargetPage) {
        this.transitionWcv.displayTransitionLoadingWCV()
      } else {
        this.transitionWcv.showTransitionLoadingWCV()
        this.transitionWcv.openTransitionWCV({
          routerPath: biz.pageLoadStatus === PageLoadStatus.Loading ? '/loading' : '/error'
        })
      }
    }
  }

  public closeTabItem(id: string, notReservedOne: boolean = false): void {
    logger.info(`closeTabItem called for id=${id}`)
    const closed = this.tabManager.closeTab(id, notReservedOne) // 假设 closeTab 返回 boolean
    if (!closed) {
      logger.info('closeTab returned false, maybe only one tab')
      return
    }
    this.businessData.delete(id)
  }

  public resizeTabItemView(): void {
    const activeId = this.tabManager.getActiveTabId()
    if (activeId) {
      const view = this.tabManager.getView(activeId)
      if (view) resetWCVSize(this.baseWindow, view)
    }

    // 如果过渡视图正在显示，调整其大小
    if (this.transitionWcv.isShowing()) {
      this.transitionWcv.showTransitionLoadingWCV()
    }
  }

  //todo:暂时不需要延时加载
  // private async scheduleBackgroundTabLoading(excludedId: string | undefined): Promise<void> {
  //   let loadIndex = 0
  //   const tabItemSettings = Object.values(this.tabItemSettings)
  //   const loadNextTab = async (): Promise<void> => {
  //     const tabItemSetting = tabItemSettings[loadIndex++]
  //     if (tabItemSetting == null || tabItemSetting.id === excludedId || !tabItemSetting.enabled || loadIndex >= this.backgroundLoadingCount) return
  //
  //     if (!this.tabManager.getView(tabItemSetting.id)) {
  //       // 后台创建标签页（不激活）
  //       await this.createTabView(tabItemSetting.id, tabItemSetting.url, tabItemSetting.type, false, false)
  //       const delay = 800 + Math.random() * 800
  //       setTimeout(loadNextTab, delay)
  //     } else {
  //       await loadNextTab()
  //     }
  //   }
  //
  //   if (typeof requestIdleCallback === 'function') {
  //     requestIdleCallback(async () => {
  //       setTimeout(loadNextTab, 500)
  //     })
  //   } else {
  //     setTimeout(loadNextTab, 800)
  //   }
  // }

  public saveTabItemSettings(): void {
    const tabs = this.tabManager.getTabs()
    const settings: Record<string, TkShopTabItemSetting> = {}
    tabs.forEach((tab) => {
      settings[tab.id] = {
        id: tab.id,
        type: tab.type,
        url: tab.url,
        focused: tab.id === this.tabManager.getActiveTabId(),
        enabled: true // 可根据需要决定，目前能显示的就是enabled
      }
    })
    // 写入存储
    const userId = this.currentState.currentUser?.userId
    if (userId) {
      logger.debug(`tabItemSetting will be saved to the user【${userId}】`)
      //logger.debug(settings)
      appStore.set(`tkShops.${userId}`, settings)
      //logger.debug(`TK 店铺${this.shopSetting.name}标签页状态已保存`)
    } else {
      logger.debug('当前用户信息为空，店铺信息无法保存')
    }
  }

  public closeTabItems(): void {
    const tabs = this.tabManager.getTabs()
    tabs.forEach((tab) => {
      this.closeTabItem(tab.id, true)
      logger.info(`close tab【${tab.title}】`)
    })
  }

  private async createTabView(id: string, url: string, type: string, activate: boolean, insertAfterActive: boolean): Promise<string | undefined> {
    const newId = this.tabManager.createTab(id, url, type, {
      hideAddress: type === TAB_TYPES.XUNDA,
      activate: activate,
      insertAfterActive: insertAfterActive,
      webPreferences: {
        partition: this.tabPersistKey
        // 其他安全设置已在 TabManager 内部设置，无需重复
      }
    })

    if (!newId) return

    const view = this.tabManager.getView(newId)
    if (!view) return

    // 附加业务监听器（加载状态、过渡动画）
    this.attachBusinessListeners(newId, view)

    return newId
  }

  private attachBusinessListeners(id: string, view: WebContentsView): void {
    // 监控导航
    // monitorNavigation(logger, view.webContents)

    ;(view.webContents as any).on('will-frame-navigate', (event: Electron.Event, url: string) => {
      if (!url.startsWith('http') && !url.startsWith('https')) {
        logger.debug(`拦截到子框架的协议跳转: ${url}`)
        event.preventDefault() // 这一步在子框架中同样有效
      }
    })

    view.webContents.on('dom-ready', () => {
      const biz = this.businessData.get(id)
      if (biz && biz.pageLoadStatus === PageLoadStatus.Loading && this.currentTabItemId === id) {
        this.transitionWcv.displayTransitionLoadingWCV()
      }
    })

    view.webContents.on('did-frame-finish-load', (_event, isMainFrame) => {
      //logger.info(`did-frame-finish-load: id=${id}, isMainFrame=${isMainFrame}, currentTabItemId=${this.currentTabItemId}`)

      if (isMainFrame) {
        const biz = this.businessData.get(id)
        if (biz) {
          biz.pageLoadStatus = PageLoadStatus.TargetPage
        }
        // 如果当前标签是激活的，隐藏过渡动画
        if (this.currentTabItemId === id) {
          //logger.info('正在调用 transitionWcv.displayTransitionLoadingWCV()')
          this.transitionWcv.displayTransitionLoadingWCV()
        } else {
          //logger.info('currentTabItemId 不匹配，不隐藏动画')
        }
      }
    })

    view.webContents.on('did-fail-provisional-load', () => {
      const biz = this.businessData.get(id)
      if (biz) {
        biz.pageLoadStatus = PageLoadStatus.ErrorPage
      }
      if (this.currentTabItemId === id) {
        this.transitionWcv.openTransitionWCV({ routerPath: '/error' })
      }
    })

    // 初始化业务数据
    this.businessData.set(id, {
      pageLoadStatus: PageLoadStatus.Loading,
      targetUrl: view.webContents.getURL()
    })
  }

  private loadTabItemSettings(): Record<string, TkShopTabItemSetting> {
    let tabItemSettings: Record<string, TkShopTabItemSetting> | null = this.currentUser == null ? null : appStore.get(`tkShops.${this.currentUser!.userId}`)
    logger.info(tabItemSettings)
    // tabItemSettings = null // todo: will be removed
    // 如果设置为空或为空对象，则新建默认 tab 设置
    if (tabItemSettings == null || Object.keys(tabItemSettings).length === 0) {
      tabItemSettings = {}
      const key = randomUUID()
      tabItemSettings[key] = {
        id: key,
        type: TAB_TYPES.TIKTOK,
        url: this.shopSetting.loginUrl,
        icon: '',
        focused: true,
        enabled: true
      } as TkShopTabItemSetting
    }
    // todo: remarked for testing
    //这里的逻辑是否是从读取到配置时，再判断一次是否超出tab最大数？如果是，则设置它的enable为false
    // else {
    //   // 删除超出 maxTabs 的项 todo:这里逻辑不太理解？是超出最大tab数？还是最大商铺数？理论上这里应该是最大tab数，然后这块通用TabManager那实现了
    //   const entries = Object.entries(tabItemSettings)
    //   let index = 0
    //   entries.forEach(([_key, setting]) => {
    //     setting.enabled = index < globalState.currentState.currentUser!.maxShopsCount
    //     index++
    //   })
    // }
    return tabItemSettings
  }
}
