/**
 * bifrost-plugins-bootstrap.ts
 *
 * Bundled Bifrost Gateway plugin installer for the Hermes desktop app.
 *
 * The desktop app ships the temga/hermes-plugin-bifrost-gateway plugins inside
 * its resources (apps/desktop/resources/bifrost-plugins/ → bundled at
 * process.resourcesPath/bifrost-plugins/ in a packaged build). On a launch
 * where the plugins were never installed, this hands the bundled copy to the
 * same Python step the installer's `bifrost-plugins` stage runs
 * (`hermes --run-module hermes_cli.bifrost_edition --from <bundle>`), which
 * copies the plugins, enables them and routes every service through Bifrost.
 *
 * - **One writer.** config.yaml is only edited by Python's save_config. A text
 *   edit here once appended a second top-level `plugins:` whenever `enabled:`
 *   was not the section's first line, and the backend refused the config.
 * - **One stamp.** `plugins/.bifrost-plugins-stamp`, written by that step, so
 *   an install that already ran the stage is a no-op here.
 * - **Offline-capable.** No network — reads from process.resourcesPath.
 * - **Non-fatal.** A failure logs a warning but never blocks app startup.
 */

import { execFile } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { promisify } from 'node:util'

import { app } from 'electron'

import { resolveInstallationLauncher } from './updater-process'
import { hiddenWindowsChildOptions } from './windows-child-options'

// ESM-safe __dirname (same fix as ru-plugins-bootstrap).
const __dirname = path.dirname(fileURLToPath(import.meta.url))

const execFileAsync = promisify(execFile)

/** Written by hermes_cli/bifrost_edition.py after a successful install. */
const STAMP_FILE = path.join('plugins', '.bifrost-plugins-stamp')
/** Stamp of desktops that installed the plugins themselves (before the Python step). */
const LEGACY_STAMP_FILE = '.bifrost-plugins-installed'

/**
 * Resolve the bundled plugin source directory.
 * Packaged: process.resourcesPath/bifrost-plugins/
 * Dev: apps/desktop/resources/bifrost-plugins/
 */
function resolveBundledPluginsDir(): string | null {
  if (process.resourcesPath) {
    const bundled = path.join(process.resourcesPath, 'bifrost-plugins')

    if (fs.existsSync(path.join(bundled, 'model-providers'))) {
      return bundled
    }
  }

  const devPath = path.resolve(__dirname, '..', 'resources', 'bifrost-plugins')

  if (fs.existsSync(path.join(devPath, 'model-providers'))) {
    return devPath
  }

  try {
    const appPathFallback = path.resolve(app.getAppPath(), 'resources', 'bifrost-plugins')

    if (fs.existsSync(path.join(appPathFallback, 'model-providers'))) {
      return appPathFallback
    }
  } catch {
    // app may be undefined in tests
  }

  return null
}

function isAlreadyInstalled(hermesHome: string): boolean {
  return [STAMP_FILE, LEGACY_STAMP_FILE].some(stamp => fs.existsSync(path.join(hermesHome, stamp)))
}

/**
 * Install bundled Bifrost plugins into ~/.hermes/plugins/ and route services
 * through Bifrost. Safe to call on every launch — no-op once a stamp exists.
 */
export async function ensureBifrostPlugins(
  hermesHome: string,
  log: (msg: string) => void = m => console.warn(`[bifrost-plugins] ${m}`)
): Promise<boolean> {
  if (isAlreadyInstalled(hermesHome)) {
    return true
  }

  const bundledDir = resolveBundledPluginsDir()

  if (!bundledDir) {
    log('Bundled Bifrost plugins directory not found — skipping (dev build without resources?)')

    return false
  }

  const installRoot = path.join(hermesHome, 'hermes-agent')
  const launcher = resolveInstallationLauncher(installRoot, process.platform === 'win32', hermesHome)

  if (!launcher) {
    log(`No hermes launcher for ${installRoot} — skipping`)

    return false
  }

  log(`Installing bundled Bifrost plugins from ${bundledDir} → ${hermesHome}/plugins/`)

  try {
    const { stdout } = await execFileAsync(
      launcher,
      ['--run-module', 'hermes_cli.bifrost_edition', '--from', bundledDir],
      hiddenWindowsChildOptions({
        cwd: installRoot,
        encoding: 'utf-8',
        env: { ...process.env, HERMES_HOME: hermesHome },
        timeout: 120_000
      })
    )

    for (const line of stdout.split('\n').filter(Boolean)) {
      log(line)
    }
  } catch (err) {
    log(`Bifrost plugin installation failed: ${(err as Error).message}`)

    return false
  }

  return isAlreadyInstalled(hermesHome)
}
