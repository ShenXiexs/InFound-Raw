function pad2(value: number): string {
  return value < 10 ? `0${value}` : `${value}`
}

function formatDate(date: Date): string {
  return `${date.getFullYear()}-${pad2(date.getMonth() + 1)}-${pad2(date.getDate())} ${pad2(date.getHours())}:${pad2(date.getMinutes())}:${pad2(date.getSeconds())}`
}

/**
 * 格式化后端返回的时间字符串，例如：
 * 2026-03-21T02:19:56.331000 -> 2026-03-21 02:19:56
 */
export function formatBackendDateTime(value?: string | null): string {
  const raw = (value || '').trim()
  if (!raw) return '-'

  const normalizedText = raw.replace('T', ' ').replace(/\.\d+$/, '')
  if (/^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2}$/.test(normalizedText)) {
    return normalizedText
  }

  const parseTarget = raw.replace(/(\.\d{3})\d+/, '$1')
  const date = new Date(parseTarget)
  if (Number.isNaN(date.getTime())) {
    return normalizedText || raw
  }

  return formatDate(date)
}
