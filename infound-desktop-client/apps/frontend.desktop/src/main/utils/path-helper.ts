import { fileURLToPath } from 'url'
import { dirname } from 'path'

const getFilePath = (): string => {
  return typeof process !== 'undefined' && process.versions?.node ? dirname(fileURLToPath(import.meta.url)) : ''
}

export { getFilePath }
