import { FrameLocator, Locator, Page } from 'playwright-core'
import { RPALocator } from '../rpa-type'

export class LocatorEngine {
  /**
   * 递归解析定位器链路
   */
  public static build(
    page: Page | FrameLocator | Locator,
    loc: RPALocator | undefined
  ): Locator | undefined {
    if (!loc) return undefined

    let element: Locator

    // 1. 根据类型创建基础定位器
    switch (loc.type) {
      case 'role':
        element = page.getByRole(loc.value as any, loc.options)
        break
      case 'text':
        element = page.getByText(loc.value, { exact: loc.options?.exact })
        break
      case 'data-test':
        element = page.locator(`[data-test="${loc.value}"]`)
        break
      default:
        element = page.locator(loc.value)
    }

    // 2. 应用过滤器 (Filters)
    if (loc.filters) {
      if (loc.filters.hasText) element = element.filter({ hasText: loc.filters.hasText })
      if (loc.filters.has) element = element.filter({ has: this.build(page, loc.filters.has) })
    }

    // 3. 递归处理链式定位 (child)
    if (loc.child) {
      return this.build(element, loc.child)
    }

    return element
  }
}
