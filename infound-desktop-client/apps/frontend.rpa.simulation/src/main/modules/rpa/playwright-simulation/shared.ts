import type { Page } from 'playwright'

export const sleep = async (ms: number): Promise<void> => {
  await new Promise((resolve) => setTimeout(resolve, ms))
}

export const evaluatePageScript = async <T>(page: Page, script: string): Promise<T> => {
  return await page.evaluate(async (source) => {
    return await (0, eval)(source)
  }, script)
}
