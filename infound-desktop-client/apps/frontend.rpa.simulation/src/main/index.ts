import { app, BrowserWindow, protocol, shell } from 'electron'
import path from 'path'
import { existsSync } from 'node:fs'
import { readFile } from 'node:fs/promises'
import { createInterface } from 'node:readline'
import { electronApp, optimizer } from '@electron-toolkit/utils'
import type { SellerChatbotPayloadInput } from '@common/types/rpa-chatbot'
import type { SellerCreatorDetailPayloadInput } from '@common/types/rpa-creator-detail'
import type { OutreachFilterConfigInput } from '@common/types/rpa-outreach'
import type { SampleManagementPayloadInput } from '@common/types/rpa-sample-management'
import type { PlaywrightSimulationPayloadInput } from '@common/types/rpa-simulation'
import { IPCManager } from './modules/ipc/base/ipc-manager'
import { RPAController } from './modules/ipc/rpa-controller'
import { LoggerController } from './modules/ipc/logger-controller'
import { appWindowsAndViewsManager } from './windows/app-windows-and-views-manager'
import { AppController } from './modules/ipc/app-controller'
import { logger } from './utils/logger'

let userDataPath = path.join(app.getPath('appData'), app.getName())
if (import.meta.env.MODE !== 'pro') {
  userDataPath = path.join(app.getPath('appData'), app.getName() + import.meta.env.MODE)
  app.commandLine.appendSwitch('ignore-certificate-errors')
}
app.setPath('userData', userDataPath)

logger.info('程序启动')

const resolveCliJsonPath = (inputPath: string): string => {
  const trimmedPath = inputPath.trim()
  if (!trimmedPath) {
    throw new Error('JSON 文件路径为空')
  }

  const candidatePaths = new Set<string>()
  if (path.isAbsolute(trimmedPath)) {
    candidatePaths.add(trimmedPath)
  } else {
    candidatePaths.add(path.resolve(process.cwd(), trimmedPath))
    candidatePaths.add(path.resolve(process.cwd(), '..', trimmedPath))
    candidatePaths.add(path.resolve(process.cwd(), '..', '..', trimmedPath))
    candidatePaths.add(path.resolve(app.getAppPath(), trimmedPath))
    candidatePaths.add(path.resolve(app.getAppPath(), '..', trimmedPath))
    candidatePaths.add(path.resolve(app.getAppPath(), '..', '..', trimmedPath))
  }

  for (const candidatePath of candidatePaths) {
    if (existsSync(candidatePath)) {
      return candidatePath
    }
  }

  throw new Error(
    `找不到 JSON 文件: ${trimmedPath}。已尝试从当前目录和仓库根目录解析，请检查路径是否存在。`
  )
}

const setupTerminalRPACLI = (rpaController: RPAController): void => {
  if (import.meta.env.MODE === 'pro') return
  if (!process.stdin.isTTY) return

  const rl = createInterface({
    input: process.stdin,
    output: process.stdout,
    prompt: 'xunda-rpa> '
  })

  const printHelp = (): void => {
    logger.info(
      '终端命令: login | start-simulation | start-simulation-headless | start-simulation-json <payload.json> | stop-simulation | sample-management [tab|tab1,tab2] | sample-management-json <payload.json> | outreach | outreach-demo | outreach-json <payload.json> | chatbot <creator_id> | chatbot-demo | chatbot-json <payload.json> | creator-detail <creator_id> | creator-detail-demo | creator-detail-json <payload.json> | help | exit'
    )
  }

  logger.info('已启用终端命令模式（可通过终端触发 RPA 指令）')
  printHelp()
  rl.prompt()

  rl.on('line', async (line) => {
    const trimmedLine = line.trim()
    const [commandToken] = trimmedLine.split(/\s+/, 1)
    const command = commandToken?.toLowerCase() || ''
    try {
      if (command === 'login') {
        await rpaController.sellerLogin()
      } else if (command === 'start-simulation') {
        await rpaController.startSimulationSession()
      } else if (command === 'start-simulation-headless') {
        await rpaController.startSimulationSession({ headless: true })
      } else if (command === 'start-simulation-json') {
        const payloadPath = trimmedLine.slice(commandToken.length).trim()
        if (!payloadPath) {
          logger.warn('缺少 JSON 文件路径，示例: start-simulation-json docs/examples/playwright-simulation-demo-payload.json')
        } else {
          const resolvedPayloadPath = resolveCliJsonPath(payloadPath)
          logger.info(`读取 Playwright 会话启动 JSON: ${resolvedPayloadPath}`)
          const fileContent = await readFile(resolvedPayloadPath, 'utf8')
          const payload = JSON.parse(fileContent) as PlaywrightSimulationPayloadInput
          await rpaController.startSimulationSession(payload)
        }
      } else if (command === 'stop-simulation') {
        await rpaController.closeSimulationSession()
      } else if (command === 'sample-management') {
        const sampleArg = trimmedLine.slice(commandToken.length).trim()
        if (!sampleArg) {
          await rpaController.runSampleManagement()
        } else {
          const tabs = sampleArg
            .split(',')
            .map((token) => token.trim())
            .filter(Boolean)
          await rpaController.runSampleManagement({
            tabs
          } as SampleManagementPayloadInput)
        }
      } else if (command === 'sample-management-json') {
        const payloadPath = trimmedLine.slice(commandToken.length).trim()
        if (!payloadPath) {
          logger.warn('缺少 JSON 文件路径，示例: sample-management-json docs/examples/sample-management-completed-payload.json')
        } else {
          const resolvedPayloadPath = resolveCliJsonPath(payloadPath)
          logger.info(`读取样品管理任务 JSON: ${resolvedPayloadPath}`)
          const fileContent = await readFile(resolvedPayloadPath, 'utf8')
          const payload = JSON.parse(fileContent) as SampleManagementPayloadInput
          await rpaController.runSampleManagement(payload)
        }
      } else if (command === 'outreach') {
        await rpaController.runSellerOutReach()
      } else if (command === 'outreach-demo') {
        await rpaController.runSellerOutReach(rpaController.getDemoOutreachPayload())
      } else if (command === 'outreach-json') {
        const payloadPath = trimmedLine.slice(commandToken.length).trim()
        if (!payloadPath) {
          logger.warn('缺少 JSON 文件路径，示例: outreach-json docs/examples/outreach-demo-payload.json')
        } else {
          const resolvedPayloadPath = resolveCliJsonPath(payloadPath)
          logger.info(`读取建联任务 JSON: ${resolvedPayloadPath}`)
          const fileContent = await readFile(resolvedPayloadPath, 'utf8')
          const payload = JSON.parse(fileContent) as OutreachFilterConfigInput
          await rpaController.runSellerOutReach(payload)
        }
      } else if (command === 'chatbot') {
        const creatorId = trimmedLine.slice(commandToken.length).trim()
        if (!creatorId) {
          logger.warn('缺少 creator_id，示例: chatbot <creator_id_demo>')
        } else {
          await rpaController.runSellerChatbot({ creatorId })
        }
      } else if (command === 'chatbot-demo') {
        await rpaController.runSellerChatbot(rpaController.getDemoSellerChatbotPayload())
      } else if (command === 'chatbot-json') {
        const payloadPath = trimmedLine.slice(commandToken.length).trim()
        if (!payloadPath) {
          logger.warn('缺少 JSON 文件路径，示例: chatbot-json docs/examples/chatbot-demo-payload.json')
        } else {
          const resolvedPayloadPath = resolveCliJsonPath(payloadPath)
          logger.info(`读取聊天机器人 JSON: ${resolvedPayloadPath}`)
          const fileContent = await readFile(resolvedPayloadPath, 'utf8')
          const payload = JSON.parse(fileContent) as SellerChatbotPayloadInput
          await rpaController.runSellerChatbot(payload)
        }
      } else if (command === 'creator-detail') {
        const creatorId = trimmedLine.slice(commandToken.length).trim()
        if (!creatorId) {
          logger.warn('缺少 creator_id，示例: creator-detail <creator_id_demo>')
        } else {
          await rpaController.runSellerCreatorDetail({ creatorId })
        }
      } else if (command === 'creator-detail-demo') {
        await rpaController.runSellerCreatorDetail(rpaController.getDemoSellerCreatorDetailPayload())
      } else if (command === 'creator-detail-json') {
        const payloadPath = trimmedLine.slice(commandToken.length).trim()
        if (!payloadPath) {
          logger.warn('缺少 JSON 文件路径，示例: creator-detail-json docs/examples/creator-detail-demo-payload.json')
        } else {
          const resolvedPayloadPath = resolveCliJsonPath(payloadPath)
          logger.info(`读取达人详情机器人 JSON: ${resolvedPayloadPath}`)
          const fileContent = await readFile(resolvedPayloadPath, 'utf8')
          const payload = JSON.parse(fileContent) as SellerCreatorDetailPayloadInput
          await rpaController.runSellerCreatorDetail(payload)
        }
      } else if (command === 'help') {
        printHelp()
      } else if (command === 'exit' || command === 'quit') {
        app.quit()
        return
      } else if (command) {
        logger.warn(`未知终端命令: ${command}`)
        printHelp()
      }
    } catch (err) {
      logger.error(`终端命令执行失败: ${(err as Error)?.message || err}`)
    }
    rl.prompt()
  })

  app.on('before-quit', () => {
    rl.close()
    void rpaController.closeSimulationSession()
  })
}

app.whenReady().then(async () => {
  protocol.handle('bytedance', () => {
    logger.warn('已从系统底层彻底拦截 bytedance 协议')
    return new Response('Protocol Blocked', { status: 403 })
  })

  const originalOpenExternal = shell.openExternal
  shell.openExternal = async (url, options) => {
    if (url.startsWith('bytedance://') || url.startsWith('ms-windows-store://')) {
      logger.error(`[安全拦截] 阻止了对外部应用的调起: ${url}`)
      return Promise.resolve() // 直接返回空，什么都不做
    }
    return originalOpenExternal(url, options)
  }

  electronApp.setAppUserModelId('if.xunda.rpa.simulation')

  // Default open or close DevTools by F12 in development
  // and ignore CommandOrControl + R in production.
  // see https://github.com/alex8088/electron-toolkit/tree/master/packages/utils
  app.on('browser-window-created', (_, window) => {
    optimizer.watchWindowShortcuts(window)
  })

  const loggerController = new LoggerController()
  const appController = new AppController()
  const rpaController = new RPAController()

  IPCManager.register(loggerController)
  IPCManager.register(appController)
  IPCManager.register(rpaController)

  await appWindowsAndViewsManager.initMainWindow()
  appWindowsAndViewsManager.mainWindow.showWindow()
  setupTerminalRPACLI(rpaController)
  app.on('before-quit', () => {
    void rpaController.closeSimulationSession()
  })

  app.on('activate', async function () {
    // On macOS it's common to re-create a window in the app when the
    // dock icon is clicked and there are no other windows open.
    if (BrowserWindow.getAllWindows().length === 0) await appWindowsAndViewsManager.initMainWindow()
  })
})

// Quit when all windows are closed, except on macOS. There, it's common
// for applications and their menu bar to stay active until the user quits
// explicitly with Cmd + Q.
app.on('window-all-closed', () => {
  if (process.platform !== 'darwin') {
    app.quit()
  }
})

// In this file you can include the rest of your app's specific main process
// code. You can also put them in separate files and require them here.
