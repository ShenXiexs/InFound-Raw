import { existsSync } from 'node:fs'
import { resolve } from 'node:path'
import { pathToFileURL } from 'node:url'

const builderMirror = 'https://github.com/electron-userland/electron-builder-binaries/releases/download/'
const requiredBrowserBundlesByTarget = {
  '--mac': [
    'build/chrome-headless-shell-mac-x64.zip',
    'build/chrome-headless-shell-mac-arm64.zip',
    'build/chrome-mac-x64.zip',
    'build/chrome-mac-arm64.zip'
  ],
  '--win': ['build/chrome-headless-shell-win64.zip', 'build/chrome-win64.zip']
}

function forceBuilderBinaryMirror() {
  process.env.NPM_CONFIG_ELECTRON_BUILDER_BINARIES_MIRROR = builderMirror
  process.env.npm_config_electron_builder_binaries_mirror = builderMirror
  process.env.ELECTRON_BUILDER_BINARIES_MIRROR = builderMirror

  delete process.env.NPM_CONFIG_ELECTRON_BUILDER_BINARIES_DOWNLOAD_OVERRIDE_URL
  delete process.env.npm_config_electron_builder_binaries_download_override_url
  delete process.env.ELECTRON_BUILDER_BINARIES_DOWNLOAD_OVERRIDE_URL
}

function clearElectronGetMirrorOverrides() {
  const electronGetOverrideVars = [
    'NPM_CONFIG_ELECTRON_MIRROR',
    'npm_config_electron_mirror',
    'npm_package_config_electron_mirror',
    'ELECTRON_MIRROR',
    'NPM_CONFIG_ELECTRON_CUSTOM_DIR',
    'npm_config_electron_custom_dir',
    'npm_package_config_electron_custom_dir',
    'ELECTRON_CUSTOM_DIR',
    'NPM_CONFIG_ELECTRON_CUSTOM_FILENAME',
    'npm_config_electron_custom_filename',
    'npm_package_config_electron_custom_filename',
    'ELECTRON_CUSTOM_FILENAME',
    'NPM_CONFIG_ELECTRON_CUSTOM_VERSION',
    'npm_config_electron_custom_version',
    'npm_package_config_electron_custom_version',
    'ELECTRON_CUSTOM_VERSION'
  ]

  for (const variableName of electronGetOverrideVars) {
    delete process.env[variableName]
  }
}

function validateBundledBrowserArchives(builderArgs) {
  const requestedTargets = Array.from(
    new Set(
      builderArgs.filter((arg) =>
        Object.prototype.hasOwnProperty.call(requiredBrowserBundlesByTarget, arg)
      )
    )
  )

  if (!requestedTargets.length) {
    return
  }

  const missingArchives = requestedTargets.flatMap((target) =>
    requiredBrowserBundlesByTarget[target]
      .map((relativePath) => resolve(relativePath))
      .filter((absolutePath) => !existsSync(absolutePath))
  )

  if (!missingArchives.length) {
    return
  }

  throw new Error(
    `Missing packaged Playwright browser archives:\n${missingArchives.map((filePath) => `- ${filePath}`).join('\n')}\nDownload them into apps/frontend.desktop/build before packaging.`
  )
}

forceBuilderBinaryMirror()
clearElectronGetMirrorOverrides()

const builderArgs = process.argv.slice(2)
validateBundledBrowserArchives(builderArgs)

const cliPath = resolve('node_modules/electron-builder/cli.js')
process.argv = [process.argv[0], cliPath, ...builderArgs]

await import(pathToFileURL(cliPath).href)
