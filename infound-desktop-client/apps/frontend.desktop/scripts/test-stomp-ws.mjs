/* eslint-disable @typescript-eslint/explicit-function-return-type */
// Debug utility script only; not part of the production WebSocket handling path.
import { Client } from '@stomp/stompjs'
import WebSocket from 'ws'

const env = process.env

const serverUrl = String(env.SERVER_URL || 'https://ws.stg.xunda.club/stomp').trim()
const token = String(env.TOKEN || '').trim()
const tokenHeader = String(env.TOKEN_HEADER || 'xunda-token').trim()
const deviceType = String(env.DEVICE_TYPE || 'client').trim()
const userId = String(env.USER_ID || '').trim()
const destinationPrefix = String(env.DESTINATION_PREFIX || '/amq/queue/user.notification')
  .trim()
  .replace(/\/+$/, '')
const reconnectDelayMs = Number(env.RECONNECT_DELAY_MS || '0') || 0
const timeoutMs = Number(env.TIMEOUT_MS || '15000') || 15000
const subscribe = String(env.SUBSCRIBE || (userId ? 'true' : 'false')).trim() === 'true'

if (!token) {
  console.error('Missing TOKEN')
  process.exit(1)
}

let timeout = null
let connected = false
let messageCount = 0

const finish = async (client, code) => {
  if (timeout) {
    clearTimeout(timeout)
    timeout = null
  }
  try {
    await client.deactivate()
  } catch {
    // ignore
  }
  process.exit(code)
}

const client = new Client({
  webSocketFactory: () =>
    new WebSocket(serverUrl, {
      headers: {
        [tokenHeader]: token,
        'xunda-device-type': deviceType
      },
      rejectUnauthorized: true
    }),
  heartbeatIncoming: 0,
  heartbeatOutgoing: 10000,
  connectHeaders: {},
  reconnectDelay: reconnectDelayMs,
  onConnect: (frame) => {
    connected = true
    console.log(`[CONNECTED] ${serverUrl}`)
    console.log(`[STOMP] session=${frame.headers.session || ''} version=${frame.headers.version || ''}`)

    if (subscribe) {
      if (!userId) {
        console.error('SUBSCRIBE=true but USER_ID is empty')
        void finish(client, 2)
        return
      }
      const destination = `${destinationPrefix}.${userId}`
      console.log(`[SUBSCRIBE] ${destination}`)
      client.subscribe(
        destination,
        (message) => {
          messageCount += 1
          console.log(`[MESSAGE ${messageCount}] destination=${destination}`)
          console.log(message.body)
          try {
            message.ack()
            console.log('[ACK] success')
          } catch (error) {
            console.error(`[ACK ERROR] ${error instanceof Error ? error.message : String(error)}`)
          }
        },
        {
          ack: 'client-individual',
          'prefetch-count': '1'
        }
      )
    }

    timeout = setTimeout(() => {
      console.log(subscribe ? `[TIMEOUT] connected but no more events within ${timeoutMs}ms, messages=${messageCount}` : `[TIMEOUT] connected within ${timeoutMs}ms`)
      void finish(client, 0)
    }, timeoutMs)
  },
  onStompError: (frame) => {
    console.error(`[STOMP ERROR] ${frame.headers.message || ''}`)
    console.error(frame.body || '')
    void finish(client, 3)
  },
  onWebSocketError: (event) => {
    console.error('[WS ERROR]')
    console.error(event)
    void finish(client, 4)
  },
  onWebSocketClose: (event) => {
    console.error(`[WS CLOSE] code=${event.code} reason=${event.reason || ''}`)
    if (!connected) {
      void finish(client, 5)
    }
  }
})

console.log(`[CONNECTING] ${serverUrl}`)
if (subscribe) {
  console.log(`[LISTENING] userId=${userId} destinationPrefix=${destinationPrefix}`)
}
client.activate()
