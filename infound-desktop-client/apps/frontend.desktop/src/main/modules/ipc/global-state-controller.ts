import { IPCGateway, IPCHandle, IPCType } from './base/ipc-decorator'
import { IPC_CHANNELS } from '@common/types/ipc-type'
import { AppState } from '@infound/desktop-base'
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
  async setGlobalState(
    pathOrPayload: string | { path?: string; value?: any },
    value?: any
  ): Promise<void> {
    const path =
      typeof pathOrPayload === 'string'
        ? pathOrPayload
        : String(pathOrPayload?.path || '')
    const resolvedValue =
      typeof pathOrPayload === 'string' ? value : pathOrPayload?.value

    if (!path) {
      return
    }

    await globalState.saveState(path, resolvedValue)
  }
}
