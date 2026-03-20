import { BaseWindow, Rectangle, screen, WebContentsView } from 'electron'

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

export { resetWCVSize, resetWCVSizeToZero, limitSize }
