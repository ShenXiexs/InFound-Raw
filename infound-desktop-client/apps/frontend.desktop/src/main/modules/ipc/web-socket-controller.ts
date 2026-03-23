import { IPCGateway, IPCHandle, IPCType } from './base/ipc-decorator'
import { IPC_CHANNELS } from '@common/types/ipc-type'
import { webSocketService } from '../../services/base/web-socket-service'
import { logger } from '../../utils/logger'

export class WebSocketController {
  @IPCHandle(IPCGateway.WS, IPC_CHANNELS.WEBSOCKET_CONNECT, IPCType.SEND)
  public async connect(): Promise<void> {
    logger.info('开始连接 WebSocket 服务器')
    await webSocketService.connect()
  }

  @IPCHandle(IPCGateway.WS, IPC_CHANNELS.WEBSOCKET_DISCONNECT, IPCType.SEND)
  public async disconnect(): Promise<void> {
    logger.info('开始断开 WebSocket 链接')
    await webSocketService.disconnect()
  }
}
