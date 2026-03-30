import { IPC_CHANNELS } from '@common/types/ipc-type'
import { logger } from '../../utils/logger'
import { appWindowsAndViewsManager } from '../../windows/app-windows-and-views-manager'
import { IPCHandle, IPCType } from './base/ipc-decorator'
import type {
  OutreachFilterConfigInput,
  PlaywrightSimulationPayloadInput,
  SampleManagementPayloadInput,
  SellerChatbotPayloadInput,
  SellerCreatorDetailPayloadInput
} from '@desktop-rpa'
import {
  PlaywrightSimulationService,
  createDemoOutreachFilterConfig,
  createDemoSellerChatbotPayload,
  createDemoSellerCreatorDetailPayload,
  isOutreachFilterConfigInput,
  isPlaywrightSimulationPayloadInput,
  isSampleManagementPayloadInput,
  isSellerChatbotPayloadInput,
  isSellerCreatorDetailPayloadInput
} from '@desktop-rpa'

const SELLER_LOGIN_URL = 'https://seller-mx.tiktok.com/'

class RPAController {
  public getSimulationService(): PlaywrightSimulationService {
    return PlaywrightSimulationService.getInstance(logger)
  }

  @IPCHandle(IPC_CHANNELS.RPA_SELLER_LOGIN, IPCType.SEND)
  async sellerLogin(): Promise<void> {
    logger.info(`启动店铺登录 RPA 任务，打开登录页: ${SELLER_LOGIN_URL}`)
    await appWindowsAndViewsManager.tkWebContentView.openView(SELLER_LOGIN_URL)
    appWindowsAndViewsManager.tkWebContentView.startSellerLoginSuccessMonitor()
  }

  public async startSimulationSession(payload?: PlaywrightSimulationPayloadInput): Promise<void> {
    await this.getSimulationService().startSession(payload)
  }

  public async closeSimulationSession(): Promise<void> {
    await this.getSimulationService().dispose()
  }

  public async runSellerOutReach(payload?: OutreachFilterConfigInput): Promise<void> {
    await this.getSimulationService().runOutreach(payload)
  }

  public async runSellerChatbot(payload?: SellerChatbotPayloadInput): Promise<void> {
    await this.getSimulationService().runChatbot(payload)
  }

  public async runSellerCreatorDetail(payload?: SellerCreatorDetailPayloadInput): Promise<void> {
    await this.getSimulationService().runCreatorDetail(payload)
  }

  public async runSampleManagement(payload?: SampleManagementPayloadInput): Promise<void> {
    await this.getSimulationService().runSampleManagement(payload)
  }

  getDemoOutreachPayload(): OutreachFilterConfigInput {
    return createDemoOutreachFilterConfig()
  }

  getDemoSellerChatbotPayload(): SellerChatbotPayloadInput {
    return createDemoSellerChatbotPayload()
  }

  getDemoSellerCreatorDetailPayload(): SellerCreatorDetailPayloadInput {
    return createDemoSellerCreatorDetailPayload()
  }

  @IPCHandle(IPC_CHANNELS.RPA_EXECUTE_SIMULATION, IPCType.SEND)
  async executeSimulation(eventOrPayload?: unknown, payloadMaybe?: PlaywrightSimulationPayloadInput): Promise<void> {
    const payload = isPlaywrightSimulationPayloadInput(payloadMaybe) ? payloadMaybe : isPlaywrightSimulationPayloadInput(eventOrPayload) ? eventOrPayload : undefined

    await this.startSimulationSession(payload)
  }

  @IPCHandle(IPC_CHANNELS.RPA_SELLER_OUT_REACH, IPCType.SEND)
  async sellerOutReach(eventOrPayload?: unknown, payloadMaybe?: OutreachFilterConfigInput): Promise<void> {
    const payload = isOutreachFilterConfigInput(payloadMaybe) ? payloadMaybe : isOutreachFilterConfigInput(eventOrPayload) ? eventOrPayload : undefined

    await this.runSellerOutReach(payload)
  }

  @IPCHandle(IPC_CHANNELS.RPA_SELLER_CHATBOT, IPCType.SEND)
  async sellerChatbot(eventOrPayload?: unknown, payloadMaybe?: SellerChatbotPayloadInput): Promise<void> {
    const payload = isSellerChatbotPayloadInput(payloadMaybe) ? payloadMaybe : isSellerChatbotPayloadInput(eventOrPayload) ? eventOrPayload : undefined

    await this.runSellerChatbot(payload)
  }

  @IPCHandle(IPC_CHANNELS.RPA_SELLER_CREATOR_DETAIL, IPCType.SEND)
  async sellerCreatorDetail(eventOrPayload?: unknown, payloadMaybe?: SellerCreatorDetailPayloadInput): Promise<void> {
    const payload = isSellerCreatorDetailPayloadInput(payloadMaybe) ? payloadMaybe : isSellerCreatorDetailPayloadInput(eventOrPayload) ? eventOrPayload : undefined

    await this.runSellerCreatorDetail(payload)
  }

  @IPCHandle(IPC_CHANNELS.RPA_SAMPLE_MANAGEMENT, IPCType.SEND)
  async sampleManagement(eventOrPayload?: unknown, payloadMaybe?: SampleManagementPayloadInput): Promise<void> {
    const payload = isSampleManagementPayloadInput(payloadMaybe) ? payloadMaybe : isSampleManagementPayloadInput(eventOrPayload) ? eventOrPayload : undefined

    await this.runSampleManagement(payload)
  }
}

export default RPAController
