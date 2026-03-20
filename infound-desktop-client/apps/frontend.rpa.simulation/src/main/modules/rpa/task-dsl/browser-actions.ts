import { TaskDefinition, TaskStepBase } from './types'

export type BrowserSelectorState = 'present' | 'visible' | 'absent' | 'hidden'
export type BrowserDataPrimitive = string | number | boolean | null
export type BrowserPaginationResult = 'moved' | 'no_more_pages'

export interface BrowserApiCollectionField {
  key: string
  path: string
  arrayItemPath?: string
  joinWith?: string
  defaultValue?: BrowserDataPrimitive
}

export type BrowserAction =
  | (TaskStepBase & {
      actionType: 'goto'
      payload: {
        url: string
        postLoadWaitMs?: number
      }
    })
  | (TaskStepBase & {
      actionType: 'waitForBodyText'
      payload: {
        text: string
        timeoutMs: number
        intervalMs?: number
      }
    })
  | (TaskStepBase & {
      actionType: 'waitForSelector'
      payload: {
        selector: string
        state?: BrowserSelectorState
        timeoutMs: number
        intervalMs?: number
      }
    })
  | (TaskStepBase & {
      actionType: 'clickSelector'
      payload: {
        selector: string
        native?: boolean
        waitForState?: BrowserSelectorState
        timeoutMs?: number
        intervalMs?: number
        postClickWaitMs?: number
      }
    })
  | (TaskStepBase & {
      actionType: 'clickByText'
      payload: {
        text: string
        fallbackTexts?: string[]
        selector: string
        exact?: boolean
        caseSensitive?: boolean
        timeoutMs?: number
        intervalMs?: number
        scrollContainerSelector?: string
        scrollStepPx?: number
        maxScrollAttempts?: number
        postClickWaitMs?: number
      }
    })
  | (TaskStepBase & {
      actionType: 'fillSelector'
      payload: {
        selector: string
        value: string
        waitForState?: BrowserSelectorState
        timeoutMs?: number
        intervalMs?: number
        clearBeforeFill?: boolean
        postFillWaitMs?: number
      }
    })
  | (TaskStepBase & {
      actionType: 'setCheckbox'
      payload: {
        selector: string
        checked?: boolean
        timeoutMs?: number
        intervalMs?: number
        scrollContainerSelector?: string
        scrollStepPx?: number
        maxScrollAttempts?: number
        postClickWaitMs?: number
      }
    })
  | (TaskStepBase & {
      actionType: 'selectDropdownSingle'
      payload: {
        triggerText: string
        triggerFallbackTexts?: string[]
        triggerSelector: string
        triggerExact?: boolean
        optionText: string
        optionSelector: string
        waitSelector?: string
        waitState?: BrowserSelectorState
        exact?: boolean
        caseSensitive?: boolean
        scrollContainerSelector?: string
        scrollStepPx?: number
        maxScrollAttempts?: number
        timeoutMs?: number
        intervalMs?: number
        triggerPostClickWaitMs?: number
        optionPostClickWaitMs?: number
        closeAfterSelect?: boolean
        closeText?: string
        closeSelector?: string
        closeWaitSelector?: string
        closeWaitState?: BrowserSelectorState
      }
    })
  | (TaskStepBase & {
      actionType: 'selectDropdownMultiple'
      payload: {
        triggerText: string
        triggerFallbackTexts?: string[]
        triggerSelector: string
        triggerExact?: boolean
        optionTexts: string[]
        optionSelector: string
        waitSelector?: string
        waitState?: BrowserSelectorState
        exact?: boolean
        caseSensitive?: boolean
        scrollContainerSelector?: string
        scrollStepPx?: number
        maxScrollAttempts?: number
        timeoutMs?: number
        intervalMs?: number
        triggerPostClickWaitMs?: number
        optionPostClickWaitMs?: number
        closeAfterSelect?: boolean
        closeText?: string
        closeSelector?: string
        continueOnMissingOptions?: boolean
        closeWaitSelector?: string
        closeWaitState?: BrowserSelectorState
      }
    })
  | (TaskStepBase & {
      actionType: 'selectCascaderOptionsByValue'
      payload: {
        triggerText: string
        triggerFallbackTexts?: string[]
        triggerSelector: string
        triggerExact?: boolean
        panelSelector: string
        values: string[]
        inputSelector?: string
        valueAttribute?: string
        scrollContainerSelector?: string
        scrollStepPx?: number
        maxScrollAttempts?: number
        timeoutMs?: number
        intervalMs?: number
        triggerPostClickWaitMs?: number
        optionPostClickWaitMs?: number
        closeAfterSelect?: boolean
        closeText?: string
        closeSelector?: string
        closeWaitSelector?: string
        closeWaitState?: BrowserSelectorState
      }
    })
  | (TaskStepBase & {
      actionType: 'fillDropdownRange'
      payload: {
        triggerText: string
        triggerFallbackTexts?: string[]
        triggerSelector: string
        triggerExact?: boolean
        waitSelector: string
        minSelector: string
        minValue: string
        maxSelector: string
        maxValue: string
        timeoutMs?: number
        intervalMs?: number
        triggerPostClickWaitMs?: number
        fillPostWaitMs?: number
        closeAfterFill?: boolean
        closeText?: string
        closeSelector?: string
        closeWaitSelector?: string
        closeWaitState?: BrowserSelectorState
      }
    })
  | (TaskStepBase & {
      actionType: 'fillDropdownThreshold'
      payload: {
        triggerText: string
        triggerFallbackTexts?: string[]
        triggerSelector: string
        triggerExact?: boolean
        waitSelector: string
        inputSelector: string
        value: string
        checkboxLabelText?: string
        checkboxLabelSelector?: string
        checkboxExact?: boolean
        timeoutMs?: number
        intervalMs?: number
        triggerPostClickWaitMs?: number
        fillPostWaitMs?: number
        checkboxPostClickWaitMs?: number
        closeAfterFill?: boolean
        closeText?: string
        closeSelector?: string
        closeWaitSelector?: string
        closeWaitState?: BrowserSelectorState
      }
    })
  | (TaskStepBase & {
      actionType: 'pressKey'
      payload: {
        key: string
        native?: boolean
        postKeyWaitMs?: number
      }
    })
  | (TaskStepBase & {
      actionType: 'assertUrlContains'
      payload: {
        keyword: string
      }
    })
  | (TaskStepBase & {
      actionType: 'startJsonResponseCapture'
      payload: {
        captureKey: string
        urlIncludes: string
        method?: string
        reset?: boolean
      }
    })
  | (TaskStepBase & {
      actionType: 'collectApiItemsByScrolling'
      payload: {
        captureKey: string
        responseListPath: string
        dedupeByPath?: string
        fields: BrowserApiCollectionField[]
        initialWaitMs?: number
        scrollContainerSelector?: string
        scrollStepPx?: number
        scrollIntervalMs?: number
        settleWaitMs?: number
        maxIdleRounds?: number
        maxScrollRounds?: number
        saveAs: string
        saveSummaryAs?: string
        saveFilePathAs?: string
        outputDir?: string
        outputFilePrefix?: string
        saveExcelFilePathAs?: string
        excelOutputDir?: string
        excelOutputFilePrefix?: string
        saveRawItemsAs?: string
        saveRawFilePathAs?: string
        saveRawDirectoryPathAs?: string
        rawOutputDir?: string
        rawOutputFilePrefix?: string
        rawDirectoryOutputDir?: string
        rawDirectoryOutputPrefix?: string
      }
    })
  | (TaskStepBase & {
      actionType: 'readText'
      payload: {
        selector: string
        saveAs: string
        timeoutMs?: number
        intervalMs?: number
        trim?: boolean
        preserveLineBreaks?: boolean
        pick?: 'first' | 'last'
        visibleOnly?: boolean
      }
    })
  | (TaskStepBase & {
      actionType: 'assertData'
      payload: {
        key: string
        equals?: BrowserDataPrimitive
        notEquals?: BrowserDataPrimitive
        contains?: string
      }
    })
  | (TaskStepBase & {
      actionType: 'waitForTextChange'
      payload: {
        selector: string
        previousKey?: string
        saveAs?: string
        timeoutMs: number
        intervalMs?: number
      }
    })

export interface BrowserTask extends Omit<TaskDefinition<BrowserAction>, 'config'> {
  config: {
    enableTrace: boolean
    retryCount: number
  }
}
