import type { TaskLoggerLike } from '@sim-rpa/task-dsl/types'
import { PlaywrightSimulationService } from '@sim-rpa/playwright-simulation/playwright-simulation-service'
import { logger } from '../../utils/logger'

export const desktopRpaExecutionService = PlaywrightSimulationService.getInstance(
  logger as unknown as TaskLoggerLike
)
