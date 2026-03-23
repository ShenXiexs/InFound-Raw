import { mkdirSync, writeFileSync } from 'node:fs'
import { join } from 'node:path'
import type {
  SellerChatbotPayload,
  SellerChatbotPayloadInput,
  SellerChatbotRecipient
} from '@sim-common/types/rpa-chatbot'
import type { BrowserAction } from '../task-dsl/browser-actions'

export const SELLER_CHATBOT_INPUT_SELECTOR =
  'textarea[data-e2e="798845f5-2eb9-0980"], textarea#imTextarea, #im_sdk_chat_input textarea, textarea[placeholder="Send a message"]'
export const SELLER_CHATBOT_SEND_BUTTON_SELECTOR =
  '#im_sdk_chat_input > div.footer-zRiuSb > div > button'
export const SELLER_CHATBOT_INPUT_COUNT_SELECTOR =
  'div[data-e2e="6981c08f-68cc-5df6"] span[data-e2e="76868bb0-0a54-15ad"]'
export const SELLER_CHATBOT_TRANSCRIPT_SELECTOR =
  'div[data-e2e="4c874cc7-9725-d612"], div.messageList-tkdtcN, div.chatd-scrollView'
const SELLER_CHATBOT_CREATOR_NAME_SELECTOR =
  'div[data-e2e="4e0becc3-a040-a9d2"], div.personInfo-qNFxKc .text-body-m-medium'
export const SELLER_CHATBOT_CREATOR_NAME_KEY = 'seller_chatbot_creator_name'
export const SELLER_CHATBOT_TRANSCRIPT_BEFORE_KEY = 'seller_chatbot_transcript_before'
export const SELLER_CHATBOT_TRANSCRIPT_AFTER_KEY = 'seller_chatbot_transcript_after'
export const SELLER_CHATBOT_INPUT_COUNT_KEY = 'seller_chatbot_input_count'
export const SELLER_CHATBOT_INPUT_COUNT_AFTER_KEY = 'seller_chatbot_input_count_after'
export const SELLER_CHATBOT_MAX_SEND_ATTEMPTS = 3

const DEFAULT_SELLER_CHATBOT_MESSAGE = 'hi'

const createDefaultSellerChatbotPayload = (): SellerChatbotPayload => ({
  creatorId: '',
  message: DEFAULT_SELLER_CHATBOT_MESSAGE,
  recipients: []
})

export const createDemoSellerChatbotPayload = (): SellerChatbotPayloadInput => ({
  creatorId: '7493999107359083121',
  message: DEFAULT_SELLER_CHATBOT_MESSAGE
})

export const mergeSellerChatbotPayload = (input?: SellerChatbotPayloadInput): SellerChatbotPayload => {
  const defaults = createDefaultSellerChatbotPayload()
  const recipients = Array.isArray(input?.recipients)
    ? input.recipients
        .filter(
          (item): item is SellerChatbotRecipient =>
            Boolean(item) && typeof item === 'object' && !Array.isArray(item)
        )
        .map((item) => ({
          creatorId: String(item.creatorId ?? '').trim(),
          message: String(item.message ?? '').trim() || undefined
        }))
        .filter((item) => Boolean(item.creatorId))
    : defaults.recipients

  return {
    creatorId: String(input?.creatorId ?? defaults.creatorId).trim(),
    message: String(input?.message ?? defaults.message).trim(),
    recipients
  }
}

export const isSellerChatbotPayloadInput = (value: unknown): value is SellerChatbotPayloadInput => {
  if (!value || typeof value !== 'object' || Array.isArray(value)) return false
  return (
    'creatorId' in (value as Record<string, unknown>) ||
    'message' in (value as Record<string, unknown>) ||
    'recipients' in (value as Record<string, unknown>)
  )
}

const buildLocalTimestamp = (): string => {
  const now = new Date()
  const year = now.getFullYear()
  const month = String(now.getMonth() + 1).padStart(2, '0')
  const day = String(now.getDate()).padStart(2, '0')
  const hour = String(now.getHours()).padStart(2, '0')
  const minute = String(now.getMinutes()).padStart(2, '0')
  const second = String(now.getSeconds()).padStart(2, '0')
  return `${year}${month}${day}_${hour}${minute}${second}`
}

export const persistSellerChatbotSessionMarkdown = (params: {
  creatorId: string
  region: string
  targetUrl: string
  creatorName: string
  message: string
  transcriptBefore: string
  transcriptAfter: string
  sendVerified: boolean
  sendAttempts: number
}): string => {
  const outputDir = join(process.cwd(), 'data/chatbot')
  mkdirSync(outputDir, { recursive: true })

  const filePath = join(outputDir, `seller_chatbot_session_${buildLocalTimestamp()}.md`)
  const transcriptChanged = params.transcriptBefore !== params.transcriptAfter

  const markdown = `# Seller Chatbot Session

- generated_at: ${new Date().toISOString()}
- creator_id: ${params.creatorId}
- creator_name: ${params.creatorName || '(empty)'}
- region: ${params.region}
- target_url: ${params.targetUrl}
- ready_signal: chat input visible
- input_selector: \`${SELLER_CHATBOT_INPUT_SELECTOR}\`
- send_button_selector: \`${SELLER_CHATBOT_SEND_BUTTON_SELECTOR}\`
- input_count_selector: \`${SELLER_CHATBOT_INPUT_COUNT_SELECTOR}\`
- transcript_selector: \`${SELLER_CHATBOT_TRANSCRIPT_SELECTOR}\`
- send_verified: ${params.sendVerified ? 'true' : 'false'}
- send_attempts: ${params.sendAttempts}
- transcript_changed_after_send: ${transcriptChanged ? 'true' : 'false'}

## Message Sent

\`\`\`text
${params.message}
\`\`\`

## Transcript Before Send

\`\`\`text
${params.transcriptBefore || '(empty)'}
\`\`\`

## Transcript After Send

\`\`\`text
${params.transcriptAfter || '(empty)'}
\`\`\`
`

  writeFileSync(filePath, markdown)
  return filePath
}

export const buildSellerChatbotPrepareSteps = (): BrowserAction[] => [
  {
    actionType: 'waitForSelector',
    payload: {
      selector: SELLER_CHATBOT_INPUT_SELECTOR,
      state: 'visible',
      timeoutMs: 30000,
      intervalMs: 250
    },
    options: { retryCount: 3 },
    onError: 'abort'
  },
  {
    actionType: 'readText',
    payload: {
      selector: SELLER_CHATBOT_CREATOR_NAME_SELECTOR,
      saveAs: SELLER_CHATBOT_CREATOR_NAME_KEY,
      timeoutMs: 5000,
      intervalMs: 250,
      trim: true
    },
    options: { retryCount: 2 },
    onError: 'continue'
  },
  {
    actionType: 'readText',
    payload: {
      selector: SELLER_CHATBOT_TRANSCRIPT_SELECTOR,
      saveAs: SELLER_CHATBOT_TRANSCRIPT_BEFORE_KEY,
      timeoutMs: 5000,
      intervalMs: 250,
      trim: true,
      preserveLineBreaks: true
    },
    options: { retryCount: 2 },
    onError: 'continue'
  }
]

export const buildSellerChatbotSendAttemptSteps = (message: string): BrowserAction[] => [
  {
    actionType: 'waitForSelector',
    payload: {
      selector: SELLER_CHATBOT_INPUT_SELECTOR,
      state: 'visible',
      timeoutMs: 10000,
      intervalMs: 250
    },
    options: { retryCount: 2 },
    onError: 'abort'
  },
  {
    actionType: 'fillSelector',
    payload: {
      selector: SELLER_CHATBOT_INPUT_SELECTOR,
      value: message,
      waitForState: 'visible',
      timeoutMs: 10000,
      intervalMs: 250,
      clearBeforeFill: true,
      postFillWaitMs: 150
    },
    options: { retryCount: 2 },
    onError: 'abort'
  },
  {
    actionType: 'readText',
    payload: {
      selector: SELLER_CHATBOT_INPUT_COUNT_SELECTOR,
      saveAs: SELLER_CHATBOT_INPUT_COUNT_KEY,
      timeoutMs: 3000,
      intervalMs: 200,
      trim: true
    },
    options: { retryCount: 1 },
    onError: 'abort'
  },
  {
    actionType: 'assertData',
    payload: {
      key: SELLER_CHATBOT_INPUT_COUNT_KEY,
      notEquals: '0'
    },
    options: { retryCount: 1 },
    onError: 'abort'
  },
  {
    actionType: 'clickSelector',
    payload: {
      selector: SELLER_CHATBOT_INPUT_SELECTOR,
      native: true,
      waitForState: 'visible',
      timeoutMs: 5000,
      intervalMs: 250,
      postClickWaitMs: 80
    },
    options: { retryCount: 1 },
    onError: 'abort'
  },
  {
    actionType: 'clickSelector',
    payload: {
      selector: SELLER_CHATBOT_SEND_BUTTON_SELECTOR,
      native: true,
      waitForState: 'visible',
      timeoutMs: 5000,
      intervalMs: 250,
      postClickWaitMs: 1500
    },
    options: { retryCount: 1 },
    onError: 'abort'
  },
  {
    actionType: 'waitForTextChange',
    payload: {
      selector: SELLER_CHATBOT_INPUT_COUNT_SELECTOR,
      previousKey: SELLER_CHATBOT_INPUT_COUNT_KEY,
      saveAs: SELLER_CHATBOT_INPUT_COUNT_AFTER_KEY,
      timeoutMs: 5000,
      intervalMs: 200
    },
    options: { retryCount: 1 },
    onError: 'continue'
  },
  {
    actionType: 'readText',
    payload: {
      selector: SELLER_CHATBOT_INPUT_COUNT_SELECTOR,
      saveAs: SELLER_CHATBOT_INPUT_COUNT_AFTER_KEY,
      timeoutMs: 3000,
      intervalMs: 200,
      trim: true
    },
    options: { retryCount: 1 },
    onError: 'continue'
  }
]

export const buildSellerChatbotFinalizeSteps = (): BrowserAction[] => [
  {
    actionType: 'readText',
    payload: {
      selector: SELLER_CHATBOT_TRANSCRIPT_SELECTOR,
      saveAs: SELLER_CHATBOT_TRANSCRIPT_AFTER_KEY,
      timeoutMs: 8000,
      intervalMs: 300,
      trim: true,
      preserveLineBreaks: true
    },
    options: { retryCount: 2 },
    onError: 'continue'
  }
]
