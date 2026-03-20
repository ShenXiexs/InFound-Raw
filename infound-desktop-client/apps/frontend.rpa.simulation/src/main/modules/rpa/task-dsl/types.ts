export interface TaskLoggerLike {
  info(message: string, ...args: unknown[]): void
  warn(message: string, ...args: unknown[]): void
  error(message: string, ...args: unknown[]): void
}

export interface TaskStepBase {
  id?: string
  actionType: string
  options?: {
    retryCount?: number
  }
  onError?: 'abort' | 'continue'
  recovery?: {
    gotoUrl?: string
    postLoadWaitMs?: number
  }
}

export interface TaskDefinition<Action extends TaskStepBase> {
  taskId: string
  taskName: string
  version?: string
  config: {
    enableTrace?: boolean
    retryCount?: number
  }
  steps: Action[]
}
