import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'

function patchStdoutForNonTty() {
  if (process.stdout.isTTY) return

  const noop = () => true

  if (typeof process.stdout.clearLine !== 'function') {
    process.stdout.clearLine = noop
  }

  if (typeof process.stdout.moveCursor !== 'function') {
    process.stdout.moveCursor = noop
  }

  if (typeof process.stdout.cursorTo !== 'function') {
    process.stdout.cursorTo = noop
  }

  if (typeof process.stdout.columns !== 'number') {
    Object.defineProperty(process.stdout, 'columns', {
      value: 80,
      writable: true,
      configurable: true
    })
  }
}

patchStdoutForNonTty()

const cliEntrypoint = resolve('node_modules/electron-vite/bin/electron-vite.js')
process.argv = [process.argv[0], cliEntrypoint, 'build', ...process.argv.slice(2)]

await import(pathToFileURL(resolve('node_modules/electron-vite/dist/cli.js')).href)
