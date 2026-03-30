import { AppInfo, AppSetting, AppState, CurrentUserInfo } from '@infound/desktop-base'
import { defineStore } from 'pinia'
import { debounce, set } from 'radash'
import { IPC_CHANNELS } from '@common/types/ipc-type'

export interface RendererState extends AppState {
  windowId: number
  isReady: boolean
}

export class RendererStore {
  private store: any
  private isSyncingFromMain = false

  private useGlobalSharedStore = defineStore('globalShared', {
    // 1. State 只放默认值，确保组件初始化不报错
    state: () => ({
      appInfo: {
        name: '',
        version: '',
        description: '',
        deviceId: '',
        sessionId: -1
      } as AppInfo,
      appSetting: {
        resourcesPath: '',
        ui: {
          tabItemLeftSize: 210,
          splitSpace: 4
        }
      } as AppSetting,
      windowId: -1,
      isUpdating: false,
      isLogin: false,
      enableDebug: false,
      currentUser: null as CurrentUserInfo | null,
      isReady: false // 增加一个加载状态标识
    }),

    actions: {
      // 2. 明确的初始化方法
      async initSync() {
        const result = await window.ipc.invoke(IPC_CHANNELS.APP_GLOBAL_STATE_GET_ALL)
        window.logger.info(`Renderer state synced: ${JSON.stringify(result.data)}`)
        if (result.success) {
          this.$patch(result.data) // 使用 $patch 批量更新
          this.isReady = true
          this.windowId = await window.ipc.getCurrentBrowserWindowId()
        }
      },

      // 3. 处理增量更新 (配合之前建议的 path + value 广播)
      updatePartialState(path: string, value: any) {
        this.$state = set(this.$state, path, value)
      }
    }
  })

  public get currentState(): RendererState {
    return this.store!
  }

  /**
   * 初始化：拉取数据并开启双向同步
   */
  public async init(): Promise<any> {
    this.store = this.useGlobalSharedStore()

    // 1. 从主进程获取初始全量数据
    await this.store.initSync()

    // 2. 开启主进程推向渲染进程的监听
    this.setupMainToRendererSync()

    // 3. 开启渲染进程推向主进程的监听
    this.setupRendererToMainSync()

    return this.store
  }

  private setupMainToRendererSync(): void {
    window.ipc.on(IPC_CHANNELS.RENDERER_MONITOR_APP_GLOBAL_STATE_SYNC, (data: { path: string; value: any }) => {
      this.isSyncingFromMain = true // 加锁

      if (data.path) {
        this.store.updatePartialState(data.path, data.value)
      } else {
        this.store.$patch(data)
      }

      this.isSyncingFromMain = false // 解锁
    })
  }

  private setupRendererToMainSync(): void {
    const debouncedSync = debounce({ delay: 500 }, (path: string, value: any) => {
      window.ipc.send(IPC_CHANNELS.APP_GLOBAL_STATE_SET_ITEM, path, value)
    })

    this.store.$subscribe((_mutation: any, state: { appSetting: any }) => {
      // 如果修改来自主进程的同步，则跳过，不发回主进程
      if (this.isSyncingFromMain) return

      // 这里可以根据需求过滤掉不需要持久化的 key
      // 假设我们只同步 appSetting 和 currentUser
      debouncedSync('appSetting', JSON.parse(JSON.stringify(state.appSetting)))
    })
  }
}

export const rendererStore = new RendererStore()
