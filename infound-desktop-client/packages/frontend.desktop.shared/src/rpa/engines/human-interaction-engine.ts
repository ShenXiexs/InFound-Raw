import { Page } from 'playwright-core'

export interface Point {
  x: number
  y: number
}

export class HumanInteractionEngine {
  private static lastPosition = { x: 0, y: 0 }

  public static async moveTo(page: Page, targetX: number, targetY: number) {
    const trajectory = this.generateTrajectory(this.lastPosition, { x: targetX, y: targetY }, 50)

    for (const point of trajectory) {
      await page.mouse.move(point.x, point.y)
      await page.waitForTimeout(15)
    }

    this.lastPosition = { x: targetX, y: targetY }
  }

  /**
   * 生成符合费茨定律的轨迹点数组
   * 采用 Ease-Out-Cubic 速度曲线，模拟靠近目标时的减速
   */
  private static generateTrajectory(start: Point, end: Point, steps: number): Point[] {
    const trajectory: Point[] = []
    const cp: Point = {
      x: start.x + (end.x - start.x) / 2 + (Math.random() - 0.5) * 100,
      y: start.y + (end.y - start.y) / 2 + (Math.random() - 0.5) * 100
    }

    for (let i = 0; i <= steps; i++) {
      const t = i / steps
      // 速度曲线：在末端减速
      const easedT = 1 - Math.pow(1 - t, 3)

      // 二次贝塞尔插值
      const x =
        Math.pow(1 - easedT, 2) * start.x +
        2 * (1 - easedT) * easedT * cp.x +
        Math.pow(easedT, 2) * end.x
      const y =
        Math.pow(1 - easedT, 2) * start.y +
        2 * (1 - easedT) * easedT * cp.y +
        Math.pow(easedT, 2) * end.y

      // 加入平滑抖动 (Perlin-like 抖动而非纯随机)
      trajectory.push({
        x: x + Math.sin(t * Math.PI) * 5,
        y: y + Math.cos(t * Math.PI) * 5
      })
    }
    return trajectory
  }
}
