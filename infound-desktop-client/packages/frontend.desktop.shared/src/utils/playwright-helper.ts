import path from 'path'
import { app } from 'electron'

const getPlaywrightBrowserPath = (headless: boolean): string => {
  // 生产环境：指向 extraResources 下的文件夹
  let browserPath = ''

  if (headless) {
    browserPath = app.isPackaged
      ? path.join(
          process.resourcesPath,
          'chromium',
          'chromium_headless_shell-1208',
          'chrome-headless-shell-win64',
          'chrome-headless-shell.exe'
        )
      : path.join(
          __dirname,
          '../../node_modules/playwright-core/.local-browsers/chromium_headless_shell-1208/chrome-headless-shell-win64/chrome-headless-shell.exe'
        )
  } else {
    browserPath = app.isPackaged
      ? path.join(process.resourcesPath, 'chromium', 'chromium-1208', 'chrome-win64', 'chrome.exe')
      : path.join(
          __dirname,
          '../../node_modules/playwright-core/.local-browsers/chromium-1208/chrome-win64/chrome.exe'
        )
  }

  return browserPath
}

export { getPlaywrightBrowserPath }
