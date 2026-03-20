export type MessageType = 'public' | 'private' | 'order'

export interface WebSocketMessage {
  type: MessageType
  data: any
}
