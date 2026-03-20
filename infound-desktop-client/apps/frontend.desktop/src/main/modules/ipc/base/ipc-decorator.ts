import 'reflect-metadata'
import { IPCChannelKey } from '@common/types/ipc-type'

export const IPC_METHOD_KEY = Symbol('IPC_METHOD_KEY')
export const IPC_TYPE_KEY = Symbol('IPC_TYPE_KEY') // 新增：标记 IPC 类型
export const IPC_GATEWAY_KEY = Symbol('IPC_GATEWAY_KEY')

export enum IPCGateway {
  APP = 'gateway:app',
  MONITOR = 'gateway:monitor',
  TK = 'gateway:tk',
  RPA = 'gateway:rpa',
  API = 'gateway:api'
}

export enum IPCType {
  INVOKE = 'invoke', // 渲染进程通过 invoke 调用主进程 (双向)
  ON = 'on', // 渲染进程通过 on 持续监听主进程 (由主进程发送)
  SEND = 'send', // 渲染进程通过 send 发送消息，主进程不需要返回值 (单向)
  ONCE = 'once' // 渲染进程只监听一次，由主进程发送
}

export function IPCHandle(gateway: IPCGateway = IPCGateway.APP, channel: IPCChannelKey, type: IPCType = IPCType.INVOKE) {
  return (target: any, propertyKey: string) => {
    Reflect.defineMetadata(IPC_GATEWAY_KEY, gateway, target, propertyKey)
    Reflect.defineMetadata(IPC_METHOD_KEY, channel, target, propertyKey)
    Reflect.defineMetadata(IPC_TYPE_KEY, type, target, propertyKey)
  }
}
