import { IPC_CHANNELS } from '@common/types/ipc-type'
import { IPCGateway, IPCHandle, IPCType } from './base/ipc-decorator'
import { taskWorkersManager } from '../rpa/task-workers-manager'
import { logger } from '../../utils/logger'

export class RPAController {
  @IPCHandle(IPCGateway.RPA, IPC_CHANNELS.RPA_TASK_START, IPCType.SEND)
  async startTask(): Promise<void> {
    logger.info('启动任务管理器')
    await taskWorkersManager.init()
  }
}
