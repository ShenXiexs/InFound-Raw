import { app } from 'electron'
import path from 'path'
import fs from 'fs'
import log from 'electron-log'

export interface LoggerOptions {
  level: 'debug' | 'info' | 'warn' | 'error'
  appName?: string
  enable?: boolean
}

export class LoggerService {
  private static instance: LoggerService
  private readonly logDir: string
  private readonly options: LoggerOptions

  private constructor(options: LoggerOptions) {
    this.options = options
    // 初始化路径
    const basePath = app.isPackaged ? path.dirname(process.execPath) : app.getAppPath()
    this.logDir = path.join(basePath, 'logs')

    if (!fs.existsSync(this.logDir)) {
      fs.mkdirSync(this.logDir, { recursive: true })
    }

    this.setup()
  }

  public static getInstance(options: LoggerOptions): LoggerService {
    if (!LoggerService.instance) {
      LoggerService.instance = new LoggerService(options)
    }
    return LoggerService.instance
  }

  // 包装后的日志方法
  public info(...args: any[]): void {
    if (this.options.enable) log.info(...args)
  }

  public warn(...args: any[]): void {
    if (this.options.enable) log.warn(...args)
  }

  public error(...args: any[]): void {
    if (this.options.enable) log.error(...args)
  }

  public debug(...args: any[]): void {
    if (this.options.enable) log.debug(...args)
  }

  private setup(): void {
    log.transports.console.level = this.options.level
    log.transports.file.level = this.options.level
    log.transports.file.maxSize = 20 * 1024 * 1024
    log.transports.file.resolvePathFn = () => {
      return path.join(this.logDir, `${new Date().toISOString().slice(0, 10)}.log`)
    }

    // 自动清理
    this.cleanupOldLogs()
    setInterval(() => this.cleanupOldLogs(), 24 * 60 * 60 * 1000)
  }

  private cleanupOldLogs(): void {
    try {
      const files = fs.readdirSync(this.logDir)
      const now = Date.now()
      files.forEach((file) => {
        const fp = path.join(this.logDir, file)
        const stat = fs.statSync(fp)
        if (now - stat.mtimeMs > 7 * 24 * 60 * 60 * 1000) {
          fs.unlinkSync(fp)
        }
      })
    } catch (e) {
      console.error('Failed to cleanup logs:', e)
    }
  }
}
