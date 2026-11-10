#!/usr/bin/env node
import { execFileSync } from 'node:child_process'
import { createHash } from 'node:crypto'
import { copyFileSync, existsSync, mkdirSync, readFileSync, realpathSync, renameSync, rmSync, statSync } from 'node:fs'
import { createRequire } from 'node:module'
import { dirname, join, resolve } from 'node:path'
import { pathToFileURL } from 'node:url'
import { parseArgs } from 'node:util'

import { lockImporters } from './pnpm-lock.mjs'

// Do not require('electron'): Electron 42's entry point can acquire a binary.
// Only this explicit preparation phase may execute the installed installer.
// `run` runs the installer; node-deps passes one that kills it once its run loses the checkout lock.
const runInstaller = (file, args, options) => execFileSync(file, args, { ...options, stdio: 'inherit' })

/** @param {{ source: string, install?: boolean, env?: NodeJS.ProcessEnv, run?: typeof runInstaller }} options @returns {string} */
export function prepareElectronRuntime({ source, install = true, env = process.env, run = runInstaller }) {
  source = resolve(source)
  const link = join(source, 'apps/desktop/node_modules/electron/package.json')
  if (!existsSync(link)) throw new Error('Missing prepared Electron dependency; install the locked desktop workspace first')
  // The workspace entry is a link into pnpm's virtual store, where Electron's own
  // dependencies (@electron-internal/extract-zip) resolve from.
  const manifest = realpathSync(link)
  const packageRoot = dirname(manifest)
  const { version, dependencies } = JSON.parse(readFileSync(manifest, 'utf8'))
  const desktop = JSON.parse(readFileSync(join(source, 'apps/desktop/package.json'), 'utf8'))
  const locked = lockImporters(readFileSync(join(source, 'pnpm-lock.yaml'), 'utf8'))['apps/desktop']?.devDependencies?.electron
  // A locked version carries its peer resolution as a suffix: 44.9.3(supports-color@10.2.2).
  const lockedVersion = locked?.version?.replace(/\(.*$/, '')
  if (version !== desktop.devDependencies?.electron || version !== lockedVersion) {
    throw new Error('Installed Electron is not the desktop lock-pinned version')
  }
  const binaryName = process.platform === 'darwin' ? 'Electron.app/Contents/MacOS/Electron'
    : process.platform === 'win32' ? 'electron.exe' : 'electron'
  const executable = join(packageRoot, 'dist', binaryName)
  const prepared = () => {
    try {
      return readFileSync(join(packageRoot, 'path.txt'), 'utf8').trim() === binaryName
        && readFileSync(join(packageRoot, 'dist/version'), 'utf8').trim().replace(/^v/, '') === version
        && statSync(executable).isFile()
    } catch {
      return false
    }
  }
  if (prepared()) return executable
  if (!install) throw new Error('Electron binary is missing or stale and lazy installs are disabled; run an explicit desktop build/update')
  const excluded = new Set(['electron_skip_binary_download', 'electron_override_dist_path',
    'electron_install_arch', 'electron_install_platform', 'npm_config_arch', 'npm_config_platform'])
  const installerEnv = Object.fromEntries(Object.entries(env).filter(([key]) => !excluded.has(key.toLowerCase())))
  Object.assign(installerEnv, { ELECTRON_INSTALL_PLATFORM: process.platform, ELECTRON_INSTALL_ARCH: process.arch,
    npm_config_platform: process.platform, npm_config_arch: process.arch })
  // install.js unpacks with @electron-internal/extract-zip, whose Windows binding imports
  // VCRUNTIME140.dll. A fresh Windows has none, so the load fails (ERR_DLOPEN_FAILED).
  // Node loads bindings with LOAD_WITH_ALTERED_SEARCH_PATH, so a copy beside the binding
  // is found first. HERMES_VC_RUNTIME is the copy our Python ships.
  if (process.platform === 'win32' && env.HERMES_VC_RUNTIME && dependencies?.['@electron-internal/extract-zip']) {
    const binding = dirname(createRequire(manifest).resolve('@electron-internal/extract-zip'))
    copyFileSync(env.HERMES_VC_RUNTIME, join(binding, 'vcruntime140.dll'))
  }
  console.log(`electron-runtime: preparing locked Electron ${version} (${process.platform}-${process.arch})...`)
  const installElectron = () => run(process.execPath, [join(packageRoot, 'install.js')], { cwd: source, env: installerEnv })
  let failure
  for (let attempt = 1; attempt <= INSTALLER_ATTEMPTS; attempt++) {
    try {
      installElectron()
      failure = undefined
      break
    } catch (error) {
      failure = error
      console.log(`electron-runtime: installer attempt ${attempt}/${INSTALLER_ATTEMPTS} failed`)
    }
  }
  if (failure) {
    try {
      seedArchiveWithCurl(packageRoot, version, installerEnv)
    } catch (error) {
      console.log(`electron-runtime: curl fallback unavailable: ${error.message}`)
      throw failure
    }
    installElectron()
  }
  if (!prepared()) throw new Error('Electron installer did not produce the prepared host runtime')
  return executable
}

// Node's downloader (install.js -> @electron/get) drops long GitHub downloads on some networks
// ("TypeError: terminated") where curl completes, which left updates owing the desktop build.
const INSTALLER_ATTEMPTS = 3

// @electron/get's own URL (mirror env included) and cache path for this host's archive, asked of
// the copy install.js runs, in the installer's environment.
const ARCHIVE_LOCATION = `
const [dist, version, platform, arch] = process.argv.slice(1)
const { pathToFileURL } = await import('node:url')
const { join } = await import('node:path')
const { getArtifactFileName, getArtifactRemoteURL } = await import(pathToFileURL(join(dist, 'artifact-utils.js')).href)
const { Cache } = await import(pathToFileURL(join(dist, 'Cache.js')).href)
const details = { version, artifactName: 'electron', platform, arch }
const url = await getArtifactRemoteURL(details)
const fileName = getArtifactFileName(details)
console.log(JSON.stringify({ url, fileName, path: new Cache(process.env.electron_config_cache || undefined).getCachePath(url, fileName) }))
`

/** Download the host archive with curl into @electron/get's cache, verified against the electron
 *  package's checksums.json (the list install.js checks), so the next install.js run unpacks it. */
function seedArchiveWithCurl(packageRoot, version, env) {
  const checksums = JSON.parse(readFileSync(join(packageRoot, 'checksums.json'), 'utf8'))
  const dist = dirname(createRequire(join(packageRoot, 'package.json')).resolve('@electron/get'))
  const { url, fileName, path } = JSON.parse(execFileSync(process.execPath,
    ['--input-type=module', '-e', ARCHIVE_LOCATION, dist, `v${version}`, process.platform, process.arch],
    { env, encoding: 'utf8' }))
  const expected = checksums[fileName]
  if (!expected) throw new Error(`no checksum for ${fileName}`)
  const partial = `${path}.partial`
  mkdirSync(dirname(path), { recursive: true })
  console.log(`electron-runtime: downloading ${fileName} with curl...`)
  execFileSync('curl', ['-fL', '--retry', '5', '--retry-all-errors', '--connect-timeout', '30', '-o', partial, url],
    { env, stdio: 'inherit' })
  const actual = createHash('sha256').update(readFileSync(partial)).digest('hex')
  if (actual !== expected) {
    rmSync(partial, { force: true })
    throw new Error(`${fileName} checksum mismatch`)
  }
  renameSync(partial, path)
}

if (process.argv[1] && import.meta.url === pathToFileURL(resolve(process.argv[1])).href) {
  const { values } = parseArgs({ options: {
    source: { type: 'string' }, 'no-install': { type: 'boolean', default: false },
  } })
  if (!values.source) throw new Error('--source is required')
  prepareElectronRuntime({ source: values.source, install: !values['no-install'] })
}
