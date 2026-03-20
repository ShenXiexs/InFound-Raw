export interface LoggerAPI {
  debug(message: string, ...args: any[]): void

  info(message: string, ...args: any[]): void

  warn(message: string, ...args: any[]): void

  error(message: string, ...args: any[]): void
}

export enum LoggerLevel {
  info,
  warn,
  error,
  debug
}
