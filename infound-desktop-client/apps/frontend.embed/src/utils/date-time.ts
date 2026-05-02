const pad2 = (value: number): string => String(value).padStart(2, '0')

const parseDateValue = (value: unknown): Date | null => {
  const text = String(value || '').trim()
  if (!text) return null

  const parsed = new Date(text)
  if (Number.isNaN(parsed.getTime())) return null
  return parsed
}

export const formatDateTimeToLocal = (value: unknown, fallback: string = '-'): string => {
  const parsed = parseDateValue(value)
  if (!parsed) {
    const text = String(value || '').trim()
    return text || fallback
  }

  return `${parsed.getFullYear()}-${pad2(parsed.getMonth() + 1)}-${pad2(parsed.getDate())} ${pad2(parsed.getHours())}:${pad2(parsed.getMinutes())}:${pad2(parsed.getSeconds())}`
}

export const formatDateTimeToLocalInput = (value: unknown, fallback: string = ''): string => {
  const parsed = parseDateValue(value)
  if (!parsed) {
    const text = String(value || '').trim()
    if (!text) return fallback

    const normalized = text.replace(' ', 'T')
    return normalized.length >= 16 ? normalized.slice(0, 16) : normalized
  }

  return `${parsed.getFullYear()}-${pad2(parsed.getMonth() + 1)}-${pad2(parsed.getDate())}T${pad2(parsed.getHours())}:${pad2(parsed.getMinutes())}`
}
