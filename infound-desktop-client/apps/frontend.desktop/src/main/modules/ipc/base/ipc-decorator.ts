import 'reflect-metadata'
import { IPCChannelKey, IPCGateway, IPCType } from '@common/types/ipc-type'

export const IPC_METHOD_KEY = Symbol('IPC_METHOD_KEY')
export const IPC_TYPE_KEY = Symbol('IPC_TYPE_KEY') // 新增：标记 IPC 类型
export const IPC_GATEWAY_KEY = Symbol('IPC_GATEWAY_KEY')

export function IPCHandle(gateway: IPCGateway = IPCGateway.APP, channel: IPCChannelKey, type: IPCType = IPCType.INVOKE) {
  return (target: any, propertyKey: string) => {
    Reflect.defineMetadata(IPC_GATEWAY_KEY, gateway, target, propertyKey)
    Reflect.defineMetadata(IPC_METHOD_KEY, channel, target, propertyKey)
    Reflect.defineMetadata(IPC_TYPE_KEY, type, target, propertyKey)
  }
}
