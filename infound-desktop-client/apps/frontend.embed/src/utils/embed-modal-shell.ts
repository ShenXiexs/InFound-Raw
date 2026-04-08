/** 与 desktop 主进程 `IPC_CHANNELS.APP_CLOSE_EMBED_MODAL` 一致 */
const APP_CLOSE_EMBED_MODAL = 'app-close-embed-modal'

const SS_EMBED_MODAL = 'xunda-embed-modal-shell'

function detectEmbedModalFromUrl(): boolean {
  try {
    if (new URLSearchParams(window.location.search).get('embedModal') === '1') {
      return true
    }
    const raw = window.location.hash.replace(/^#/, '') || ''
    const qPart = raw.includes('?') ? raw.split('?')[1] : ''
    return new URLSearchParams(qPart).get('embedModal') === '1'
  } catch {
    return false
  }
}

/**
 * 在 App 入口调用一次：首屏 URL 带 `embedModal=1` 时写入 sessionStorage，
 * 避免侧栏切换 hash 后丢失参数导致又出现「返回一键建联」。
 */
export function initEmbedModalShellFromUrl(): void {
  if (!detectEmbedModalFromUrl()) {
    return
  }
  try {
    sessionStorage.setItem(SS_EMBED_MODAL, '1')
  } catch {
    // ignore
  }
}

/**
 * 是否为桌面模态 BrowserWindow 内的 embed（与店铺标签内全屏 embed 区分）
 */
export function isEmbedModalShell(): boolean {
  try {
    if (sessionStorage.getItem(SS_EMBED_MODAL) === '1') {
      return true
    }
  } catch {
    // ignore
  }
  return detectEmbedModalFromUrl()
}

/**
 * 关闭模态 embed 窗口：优先走主进程 IPC；失败时在模态壳内回退为 `window.close()`
 */
export async function requestCloseEmbedModalShell(): Promise<void> {
  const invoke = (window as any).ipc?.invoke as ((ch: string, ...args: any[]) => Promise<any>) | undefined
  if (typeof invoke === 'function') {
    try {
      await invoke(APP_CLOSE_EMBED_MODAL)
      return
    } catch {
      // 忽略
    }
  }
  if (isEmbedModalShell()) {
    window.close()
  }
}
