const WINDOWS_DRIVE_PATH_REGEX = /^[a-zA-Z]:\//

export function toFileUrl(filePath: string): string {
  const trimmedPath = filePath?.trim() || ''
  if (!trimmedPath) return ''

  const normalizedPath = trimmedPath.replace(/\\/g, '/')
  const absolutePath = WINDOWS_DRIVE_PATH_REGEX.test(normalizedPath)
    ? `/${normalizedPath}`
    : normalizedPath.startsWith('/')
      ? normalizedPath
      : `/${normalizedPath}`

  return encodeURI(`file://${absolutePath}`)
}

export function resolveResourceAssetUrl(resourcesPath: string, fileName: string): string {
  const basePath = (resourcesPath || '').trim().replace(/[\\/]+$/, '')
  const assetName = (fileName || '').trim().replace(/^[/\\]+/, '')
  if (!basePath || !assetName) return ''
  return toFileUrl(`${basePath}/${assetName}`)
}

