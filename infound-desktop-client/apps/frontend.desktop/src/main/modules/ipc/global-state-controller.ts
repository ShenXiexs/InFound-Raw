import { IPCGateway, IPCHandle, IPCType } from './base/ipc-decorator'
import { IPC_CHANNELS } from '@common/types/ipc-type'
import { AppState } from '@infound/desktop-shared'
import { globalState } from '../state/global-state'

export class GlobalStateController {
  @IPCHandle(IPCGateway.APP, IPC_CHANNELS.APP_GLOBAL_STATE_GET_ALL, IPCType.INVOKE)
  async getGlobalState(): Promise<{ success: boolean; data: AppState }> {
    return {
      success: true,
      data: globalState.currentState
    }
  }

  @IPCHandle(IPCGateway.APP, IPC_CHANNELS.APP_GLOBAL_STATE_SET_ITEM, IPCType.SEND)
  async setGlobalState(path: string, value: any): Promise<void> {
    await globalState.saveState(path, value)
  }
}
