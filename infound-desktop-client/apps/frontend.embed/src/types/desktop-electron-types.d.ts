declare module '@infound/desktop-electron/types' {
  export interface LoggerAPI {
    debug(message: string, ...args: any[]): void
    info(message: string, ...args: any[]): void
    warn(message: string, ...args: any[]): void
    error(message: string, ...args: any[]): void
  }

  export type LoggerLevel = number
}
