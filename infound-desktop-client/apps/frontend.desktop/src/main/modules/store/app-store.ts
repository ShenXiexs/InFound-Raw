import { createHash } from 'crypto'
import { app } from 'electron'
import pkg from 'node-machine-id'
//import Store from 'electron-store'
import Store from 'electron-store'
import { AppStoreSchema, CurrentUserInfo } from '@infound/desktop-base'
import { AppConfig } from '@common/app-config'
import { logger } from '../../utils/logger'
import { credentialStore } from './credential-store'

const { machineIdSync } = pkg

const defaultData: AppStoreSchema = {
  appSetting: {
    resourcesPath: '',
    ui: {
      tabItemLeftSize: 210,
      splitSpace: 4
    }
  },
  currentUser: {
    userId: '00000000-0000-0000-0000-000000000001',
    username: 'demo',
    email: undefined,
    phoneNumber: undefined,
    avatar: undefined,
    nickname: undefined,
    tokenName: '',
    tokenValue: '',
    startTime: 0,
    endTime: 0,
    maxShopsCount: 5,
    updateTime: 0,
    enableDebug: false,
    inviteCode: ''
  } as CurrentUserInfo,
  apiCookie: undefined
}

// 客户端数据持久化
export class AppStore {
  private store!: Store<AppStoreSchema>
  private schema: Store.Schema<AppStoreSchema> = {
    appSetting: {
      type: 'object',
      properties: {
        ui: {
          type: 'object',
          properties: {
            tabItemLeftSize: { type: 'number' },
            splitSpace: { type: 'number' }
          }
        }
      }
    },
    currentUser: {
      type: ['object', 'null'],
      properties: {
        userId: { type: 'string' },
        username: { type: 'string' },
        permission: {
          type: ['object', 'null'],
          properties: {
            availableCount: { type: 'number' },
            availableStartDate: { type: 'string' },
            availableEndDate: { type: 'string' },
            enableDebug: { type: 'boolean' },
            startTime: { type: 'string' },
            endTime: { type: 'string' },
            maxTabs: { type: 'number' }
          }
        },
        email: { type: ['string', 'null'] },
        phoneNumber: { type: ['string', 'null'] },
        avatar: { type: ['string', 'null'] },
        nickname: { type: ['string', 'null'] },
        tokenName: { type: 'string' },
        tokenValue: { type: 'string' },
        startTime: { type: 'number' },
        endTime: { type: 'number' },
        maxShopsCount: { type: 'number' },
        updateTime: { type: 'number' },
        enableDebug: { type: 'boolean' },
        inviteCode: { type: 'string' }
      }
    },
    apiCookie: {
      anyOf: [{ type: 'null' }, { type: 'string' }, { type: 'array', items: { type: 'string' } }]
    },
    deviceId: {
      anyOf: [{ type: 'null' }, { type: 'string' }]
    }
  }

  /*constructor() {
    const storeName = AppConfig.IS_PRO ? 'app' : 'app-' + import.meta.env.MODE
    logger.info('AppStore init', app.getPath('userData'), storeName)

    this.store = new Store<AppStoreSchema>({
      cwd: app.getPath('userData'),
      name: storeName,
      fileExtension: 'json',
      clearInvalidConfig: true,
      schema: this.schema,
      defaults: defaultData,
      encryptionKey: AppConfig.IS_PRO ? this.getDeviceEncryptionKey() : undefined
      /!*migrations: {
        '1.0.1': (store) => {
          const appInfo = store.get('appInfo')
          if (appInfo) {
            store.set('appSetting', appInfo)
          }
        }
      }*!/
    })
  }*/

  // 【核心】提供一个异步的初始化方法
  public async init(): Promise<void> {
    const storeName = AppConfig.IS_PRO ? 'app' : 'app-' + import.meta.env.MODE

    this.store = new Store<AppStoreSchema>({
      cwd: app.getPath('userData'),
      name: storeName,
      fileExtension: 'json',
      clearInvalidConfig: true,
      schema: this.schema,
      defaults: defaultData,
      encryptionKey: AppConfig.IS_PRO ? this.getDeviceEncryptionKey() : undefined
      /*migrations: {
          '1.0.1': (store) => {
            const appInfo = store.get('appInfo')
            if (appInfo) {
              store.set('appSetting', appInfo)
            }
          }
        }*/
    })
  }

  public set(path: string, value: any): void {
    logger.debug('AppStore set key', path)
    if (path === 'currentUser.tokenValue') {
      credentialStore.saveToken(value).then(() => {})
    } else {
      this.store.set(path, value)
    }
  }

  public get<T>(path: string, defaultValue?: T): T {
    if (path === 'currentUser.tokenValue') {
      let token: string = ''
      credentialStore.getToken().then((t) => (token = t || ''))
      return (token || '') as T
    } else {
      return this.store.get(path, defaultValue) as T
    }
  }

  private getDeviceEncryptionKey(): string {
    const salt = AppConfig.APP_HARDCODED_SALT
    const hwid = machineIdSync(true)
    return createHash('sha256')
      .update(hwid + salt)
      .digest('hex')
  }
}

export const appStore = new AppStore()
