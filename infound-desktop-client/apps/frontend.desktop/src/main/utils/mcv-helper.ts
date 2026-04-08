import { app, BaseWindow, Rectangle, screen, WebContentsView } from 'electron'

const resetWCVSize = (baseWindow: BaseWindow, view: WebContentsView): void => {
  const [contentWidth, contentHeight] = baseWindow.getContentSize()
  const width = contentWidth
  const height = contentHeight

  //const [width, height] = baseWindow.getSize()
  const headerHeight = 90

  view.setBounds({
    x: 0,
    y: headerHeight,
    width: width,
    height: height - headerHeight
  })

  if (!view.getVisible()) {
    view.setVisible(true)
  }
}

const resetWCVSizeToZero = (view: WebContentsView): void => {
  if (view != null) {
    //view.setBounds({ x: 0, y: 0, width: 0, height: 0 })
    view.setVisible(false)
  }
}

const limitSize = (bounds: Rectangle): Rectangle => {
  const mainScreen = screen.getPrimaryDisplay()
  const { width: displayWidth, height: displayHeight } = mainScreen.workAreaSize
  const { x, y, width, height } = bounds
  return {
    x: Math.max(0, x),
    y: Math.max(0, y),
    width: Math.min(width, displayWidth),
    height: Math.min(height, displayHeight)
  }
}

/**
 * 清理 User-Agent，移除暴露 Electron 和应用信息的部分
 * 使其看起来像普通的 Chrome 浏览器
 */
const getCleanUserAgent = (): string => {
  const nativeUA = app.userAgentFallback

  // 原始 UA 格式示例：
  // Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) infound-desktop-client/0.0.35 Chrome/143.0.7499.147 Electron/36.3.2 Safari/537.36

  // 需要移除的部分：
  // 1. 应用名称和版本号（如 infound-desktop-client/0.0.35）
  // 2. Electron 版本标识（如 Electron/36.3.2）

  // 使用正则表达式匹配并移除这些部分
  const cleanedUA = nativeUA
    // 移除 "应用名/版本号" 格式的部分
    .replace(/\s[a-zA-Z0-9_-]+\/\d+\.\d+\.\d+(?=\s)/g, '')
    // 移除 "Electron/版本号" 部分
    .replace(/\sElectron\/[\d.]+/g, '')

  // 清理后应该只剩下标准浏览器的 UA
  // Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/143.0.7499.147 Safari/537.36

  return cleanedUA.trim()
}

export { resetWCVSize, resetWCVSizeToZero, limitSize, getCleanUserAgent }
