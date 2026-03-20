import { WebContents } from 'electron'
import type { SampleManagementRow } from './types'
import {
  SAMPLE_DRAWER_CLOSE_SELECTOR,
  SAMPLE_DRAWER_SELECTOR,
  SAMPLE_NEXT_SELECTOR,
  SAMPLE_TABLE_SELECTOR
} from './config'

const sleep = (ms: number) => new Promise((resolve) => setTimeout(resolve, ms))

export async function reloadCurrentPage(webContents: WebContents): Promise<void> {
  await new Promise<void>((resolve) => {
    let settled = false
    const timer = setTimeout(() => finish(), 30000)
    const finish = () => {
      if (settled) return
      settled = true
      clearTimeout(timer)
      resolve()
    }

    webContents.once('did-finish-load', finish)
    try {
      webContents.reload()
    } catch {
      finish()
    }
  })
}

export async function waitForSamplePageReady(webContents: WebContents): Promise<boolean> {
  const timeoutMs = 30000
  const startedAt = Date.now()

  while (Date.now() - startedAt < timeoutMs) {
    const ready = await webContents.executeJavaScript(
      `(() => {
        const normalize = (value) => String(value ?? '').replace(/\\s+/g, ' ').trim().toLowerCase()
        const href = String(location.href || '')
        const bodyText = normalize(document.body?.innerText || '')
        const expectedLabels = ['to review', 'ready to ship', 'shipped', 'in progress', 'completed']
        const tabTexts = Array.from(document.querySelectorAll('[role="tab"], .arco-tabs-header-title'))
          .map((node) => normalize(node.textContent))
          .filter(Boolean)
        const matchedLabels = expectedLabels.filter(
          (label) => bodyText.includes(label) || tabTexts.some((text) => text.includes(label))
        )
        const hasTable = Boolean(document.querySelector(${JSON.stringify(SAMPLE_TABLE_SELECTOR)}))
        return href.includes('/product/sample-request') && (hasTable || matchedLabels.length >= 2 || tabTexts.length >= 3)
      })()`,
      true
    )

    if (Boolean(ready)) {
      return true
    }

    await sleep(250)
  }

  return false
}

export async function ensureTabSelected(webContents: WebContents, label: string): Promise<boolean> {
  return Boolean(
    await webContents.executeJavaScript(
      `(() => {
        const targetLabel = ${JSON.stringify(label)}
        const normalize = (value) => String(value ?? '').replace(/\s+/g, ' ').trim().toLowerCase()
        const expected = normalize(targetLabel)
        const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
        const extractTitle = (node) =>
          normalize(node.querySelector('.m4b-tabs-pane-title-content')?.textContent || node.textContent).replace(/\s*\d+\s*$/, '')
        const isSelected = (node) =>
          node.getAttribute('aria-selected') === 'true' || String(node.getAttribute('class') || '').includes('arco-tabs-header-title-active')

        return (async () => {
          const tabs = Array.from(document.querySelectorAll('[role="tab"], .arco-tabs-header-title'))
          const target = tabs.find((node) => extractTitle(node) === expected)
          if (!target) return false
          if (!isSelected(target)) {
            const html = target instanceof HTMLElement ? target : target.querySelector('.m4b-tabs-pane-title-content') || target
            if (html instanceof HTMLElement) {
              html.click()
            } else if (typeof target.click === 'function') {
              target.click()
            } else {
              target.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
            }
            await sleep(1000)
          }
          return isSelected(target)
        })()
      })()`,
      true
    )
  )
}

export async function clickPaginationNext(webContents: WebContents): Promise<boolean> {
  return Boolean(
    await webContents.executeJavaScript(
      `(() => {
        const nextButton = document.querySelector(${JSON.stringify(SAMPLE_NEXT_SELECTOR)})
        if (!nextButton) return false
        const className = String(nextButton.getAttribute('class') || '')
        const disabled = nextButton.getAttribute('aria-disabled') === 'true' || className.includes('arco-pagination-item-disabled')
        if (disabled) return false
        if (typeof nextButton.click === 'function') {
          nextButton.click()
        } else {
          nextButton.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }))
        }
        return true
      })()`,
      true
    )
  )
}

export async function waitForSelectorState(
  webContents: WebContents,
  selector: string,
  state: 'present' | 'visible' | 'absent' | 'hidden',
  timeoutMs: number,
  intervalMs: number
): Promise<boolean> {
  return Boolean(
    await webContents.executeJavaScript(
      `(() => {
        const selector = ${JSON.stringify(selector)}
        const state = ${JSON.stringify(state)}
        const timeoutMs = ${JSON.stringify(timeoutMs)}
        const intervalMs = ${JSON.stringify(intervalMs)}

        const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms))
        const isVisible = (element) => {
          if (!(element instanceof HTMLElement)) return false
          const style = window.getComputedStyle(element)
          if (style.display === 'none' || style.visibility === 'hidden') return false
          return element.offsetParent !== null || style.position === 'fixed'
        }
        const match = () => {
          const nodes = Array.from(document.querySelectorAll(selector))
          if (state === 'present') return nodes.length > 0
          if (state === 'visible') return nodes.some((node) => isVisible(node))
          if (state === 'absent') return nodes.length === 0
          if (state === 'hidden') return nodes.length > 0 && nodes.every((node) => !isVisible(node))
          return false
        }

        return (async () => {
          const startedAt = Date.now()
          while (Date.now() - startedAt < timeoutMs) {
            if (match()) return true
            await sleep(intervalMs)
          }
          return false
        })()
      })()`,
      true
    )
  )
}

export async function openCompletedViewContentDrawer(
  webContents: WebContents,
  row: SampleManagementRow,
  rowIndex: number
): Promise<boolean> {
  return Boolean(
    await webContents.executeJavaScript(
      `(() => {
        const rowIndex = ${JSON.stringify(rowIndex)}
        const creatorName = ${JSON.stringify(row.creator_name)}
        const productName = ${JSON.stringify(row.product_name)}
        const normalize = (value) => String(value ?? '').replace(/\s+/g, ' ').trim().toLowerCase()
        const isVisible = (node) => {
          if (!(node instanceof HTMLElement)) return false
          const style = window.getComputedStyle(node)
          if (style.display === 'none' || style.visibility === 'hidden') return false
          return node.offsetParent !== null || style.position === 'fixed'
        }

        const rows = Array.from(document.querySelectorAll('tr.arco-table-tr')).filter(isVisible)
        const expectedCreator = normalize(creatorName)
        const expectedCreatorAt = expectedCreator.startsWith('@') ? expectedCreator : '@' + expectedCreator
        const expectedProduct = normalize(productName)

        const targetRow =
          rows.find((rowNode) => {
            const text = normalize(rowNode.textContent)
            const creatorMatched = !expectedCreator || text.includes(expectedCreator) || text.includes(expectedCreatorAt)
            const productMatched = !expectedProduct || text.includes(expectedProduct)
            return creatorMatched && productMatched
          }) || rows[rowIndex] || null

        if (!(targetRow instanceof HTMLElement)) {
          return false
        }

        targetRow.scrollIntoView({ block: 'center', inline: 'nearest' })
        const actionNodes = Array.from(targetRow.querySelectorAll('div[data-e2e="e197794d-b324-d3da"]'))
        const viewContentNode =
          actionNodes.find((node) => normalize(node.textContent).includes('view content')) || null
        if (!(viewContentNode instanceof HTMLElement)) {
          return false
        }

        viewContentNode.scrollIntoView({ block: 'center', inline: 'nearest' })
        viewContentNode.click()
        return true
      })()`,
      true
    )
  )
}

export async function clickDrawerTabByText(webContents: WebContents, label: string): Promise<boolean> {
  return Boolean(
    await webContents.executeJavaScript(
      `(() => {
        const label = ${JSON.stringify(label)}
        const normalize = (value) => String(value ?? '').replace(/\s+/g, ' ').trim().toLowerCase()
        const isVisible = (node) => {
          if (!(node instanceof HTMLElement)) return false
          const style = window.getComputedStyle(node)
          if (style.display === 'none' || style.visibility === 'hidden') return false
          return node.offsetParent !== null || style.position === 'fixed'
        }

        const drawers = Array.from(document.querySelectorAll(${JSON.stringify(SAMPLE_DRAWER_SELECTOR)})).filter(isVisible)
        const drawer = drawers[drawers.length - 1]
        if (!(drawer instanceof HTMLElement)) {
          return false
        }

        const tabs = Array.from(drawer.querySelectorAll('[role="tab"], .arco-tabs-header-title'))
        const target = tabs.find((tab) => normalize(tab.textContent).includes(normalize(label)))
        if (!(target instanceof HTMLElement)) {
          return false
        }

        target.scrollIntoView({ block: 'nearest', inline: 'nearest' })
        target.click()
        return true
      })()`,
      true
    )
  )
}

export async function closeDrawerIfOpen(webContents: WebContents): Promise<void> {
  const closed = await webContents.executeJavaScript(
    `(() => {
      const isVisible = (node) => {
        if (!(node instanceof HTMLElement)) return false
        const style = window.getComputedStyle(node)
        if (style.display === 'none' || style.visibility === 'hidden') return false
        return node.offsetParent !== null || style.position === 'fixed'
      }
      const closeNode = Array.from(document.querySelectorAll(${JSON.stringify(SAMPLE_DRAWER_CLOSE_SELECTOR)})).find(isVisible)
      if (!(closeNode instanceof HTMLElement)) {
        return false
      }
      closeNode.click()
      return true
    })()`,
    true
  )

  if (closed) {
    await waitForSelectorState(webContents, SAMPLE_DRAWER_SELECTOR, 'absent', 5000, 150)
  }
}
