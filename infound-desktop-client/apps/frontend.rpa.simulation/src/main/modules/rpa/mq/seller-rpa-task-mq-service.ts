import type {
  SellerRpaChatMqMessage,
  SellerRpaCreatorDetailMqMessage,
  SellerRpaInternalQueueName,
  SellerRpaMqMessage,
  SellerRpaOutreachMqMessage,
  SellerRpaSampleMqMessage
} from '@sim-common/types/seller-rpa-mq'
import type { SellerCreatorDetailData } from '@sim-common/types/rpa-creator-detail'
import type { SampleManagementExportResult } from '../sample-management/types'
import { logger } from '../../../utils/logger'

export interface SellerRpaChatMqResult {
  creatorId: string
  creatorName: string
  message: string
  send: 0 | 1
  sendTime?: string
  errorMessage?: string
}

export interface SellerRpaTaskMqExecutor {
  executeOutreachMqMessage(message: SellerRpaOutreachMqMessage): Promise<void>
  executeCreatorDetailMqMessage(
    message: SellerRpaCreatorDetailMqMessage
  ): Promise<SellerCreatorDetailData>
  executeChatMqMessage(message: SellerRpaChatMqMessage): Promise<SellerRpaChatMqResult[]>
  executeSampleMqMessage(message: SellerRpaSampleMqMessage): Promise<SampleManagementExportResult>
}

export class SellerRpaTaskMqService {
  private static instance: SellerRpaTaskMqService | null = null

  public static getInstance(): SellerRpaTaskMqService {
    if (!SellerRpaTaskMqService.instance) {
      SellerRpaTaskMqService.instance = new SellerRpaTaskMqService()
    }
    return SellerRpaTaskMqService.instance
  }

  private executor: SellerRpaTaskMqExecutor | null = null
  private queueChains = new Map<SellerRpaInternalQueueName, Promise<unknown>>()

  private constructor() {
    this.resetQueueChains()
  }

  public start(executor: SellerRpaTaskMqExecutor): void {
    this.executor = executor
    this.resetQueueChains()
    logger.info('[seller-rpa-mq] 已启动客户端内部 MQ 服务: queues=outreach,creator_detail,chat,sample')
  }

  public stop(): void {
    this.executor = null
    this.resetQueueChains()
    logger.info('[seller-rpa-mq] 已停止客户端内部 MQ 服务')
  }

  public publishOutreach(message: SellerRpaOutreachMqMessage): Promise<void> {
    return this.publish('outreach', message) as Promise<void>
  }

  public publishForTesting(message: SellerRpaMqMessage): Promise<unknown> {
    switch (message.queue) {
      case 'outreach':
        return this.publishOutreach(message)
      case 'creator_detail':
        return this.publishCreatorDetail(message)
      case 'chat':
        return this.publishChat(message)
      case 'sample':
        return this.publishSample(message)
      default:
        throw new Error(`unsupported seller rpa mq queue: ${(message as SellerRpaMqMessage).queue}`)
    }
  }

  public publishCreatorDetail(
    message: SellerRpaCreatorDetailMqMessage
  ): Promise<SellerCreatorDetailData> {
    return this.publish('creator_detail', message) as Promise<SellerCreatorDetailData>
  }

  public async publishCreatorDetailBatch(
    messages: SellerRpaCreatorDetailMqMessage[]
  ): Promise<SellerCreatorDetailData[]> {
    return Promise.all(messages.map((message) => this.publishCreatorDetail(message)))
  }

  public publishChat(message: SellerRpaChatMqMessage): Promise<SellerRpaChatMqResult[]> {
    return this.publish('chat', message) as Promise<SellerRpaChatMqResult[]>
  }

  public async publishChatBatch(
    messages: SellerRpaChatMqMessage[]
  ): Promise<SellerRpaChatMqResult[]> {
    const results = await Promise.all(messages.map((message) => this.publishChat(message)))
    return results.flat()
  }

  public publishSample(
    message: SellerRpaSampleMqMessage
  ): Promise<SampleManagementExportResult> {
    return this.publish('sample', message) as Promise<SampleManagementExportResult>
  }

  private publish<T>(
    queue: SellerRpaInternalQueueName,
    message: SellerRpaMqMessage
  ): Promise<T> {
    const executor = this.executor
    if (!executor) {
      throw new Error('seller rpa mq executor is not started')
    }

    const previous = this.queueChains.get(queue) ?? Promise.resolve()
    const task = previous.then(async () => {
      logger.info(
        `[seller-rpa-mq] 开始消费消息: queue=${queue} source=${message.metadata?.source || 'unknown'} task_id=${this.resolveTaskId(message)}`
      )
      const result = await this.consume(executor, message)
      logger.info(
        `[seller-rpa-mq] 消费完成: queue=${queue} source=${message.metadata?.source || 'unknown'} task_id=${this.resolveTaskId(message)}`
      )
      return result as T
    })

    this.queueChains.set(queue, task.then(() => undefined, () => undefined))
    return task
  }

  private async consume(
    executor: SellerRpaTaskMqExecutor,
    message: SellerRpaMqMessage
  ): Promise<unknown> {
    switch (message.queue) {
      case 'outreach':
        return executor.executeOutreachMqMessage(message)
      case 'creator_detail':
        return executor.executeCreatorDetailMqMessage(message)
      case 'chat':
        return executor.executeChatMqMessage(message)
      case 'sample':
        return executor.executeSampleMqMessage(message)
      default:
        throw new Error(`unsupported seller rpa mq queue: ${(message as SellerRpaMqMessage).queue}`)
    }
  }

  private resetQueueChains(): void {
    this.queueChains.set('outreach', Promise.resolve())
    this.queueChains.set('creator_detail', Promise.resolve())
    this.queueChains.set('chat', Promise.resolve())
    this.queueChains.set('sample', Promise.resolve())
  }

  private resolveTaskId(message: SellerRpaMqMessage): string {
    const taskId = String(message.payload.taskId || '').trim()
    if (taskId) {
      return taskId
    }
    return String(message.metadata?.messageId || '').trim() || '(no-task-id)'
  }
}
