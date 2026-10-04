/**
 * bifrost-plugins-bootstrap.ts
 *
 * Bifrost edition first-launch step for the Hermes desktop app.
 *
 * The Bifrost Gateway plugins ship inside the agent tree
 * (`plugins/<category>/bifrost/`) and update with it. On a launch where the
 * services were never routed through Bifrost, or where a home still holds the
 * plugin copies older builds put in `plugins/`, this runs the same Python step
 * the installer's `bifrost-plugins` stage runs
 * (`hermes --run-module hermes_cli.bifrost_edition`): it removes those copies
 * (they would shadow the bundled plugins) and configures the services once.
 *
 * - **One writer.** config.yaml is only edited by Python's save_config. A text
 *   edit here once appended a second top-level `plugins:` whenever `enabled:`
 *   was not the section's first line, and the backend refused the config.
 * - **One stamp.** `plugins/.bifrost-plugins-stamp`, written by that step, so
 *   an install that already ran the stage is a no-op here.
 * - **Non-fatal.** A failure logs a warning but never blocks app startup.
 */

import { execFile } from 'node:child_process'
import fs from 'node:fs'
import path from 'node:path'
import { promisify } from 'node:util'

import { resolveInstallationLauncher } from './updater-process'
import { hiddenWindowsChildOptions } from './windows-child-options'

const execFileAsync = promisify(execFile)

/** Written by hermes_cli/bifrost_edition.py once the services are configured. */
const STAMP_FILE = path.join('plugins', '.bifrost-plugins-stamp')
/** Stamp of desktops that configured the services themselves (before the Python step). */
const LEGACY_STAMP_FILE = '.bifrost-plugins-installed'
/** Where older builds copied the plugins; mirrors BIFROST_PLUGINS in hermes_cli/bifrost_edition.py. */
const LEGACY_PLUGIN_COPIES = ['model-providers', 'image_gen', 'web', 'transcription', 'tts'].map(category =>
  path.join('plugins', category, 'bifrost')
)

function needsBifrostStep(hermesHome: string): boolean {
  const configured = [STAMP_FILE, LEGACY_STAMP_FILE].some(stamp => fs.existsSync(path.join(hermesHome, stamp)))

  return !configured || LEGACY_PLUGIN_COPIES.some(copy => fs.existsSync(path.join(hermesHome, copy)))
}

/**
 * Route services through Bifrost and drop pre-bundle plugin copies.
 * Safe to call on every launch — no-op once configured and clean.
 */
export async function ensureBifrostPlugins(
  hermesHome: string,
  log: (msg: string) => void = m => console.warn(`[bifrost-plugins] ${m}`)
): Promise<boolean> {
  if (!needsBifrostStep(hermesHome)) {
    return true
  }

  const installRoot = path.join(hermesHome, 'hermes-agent')
  const launcher = resolveInstallationLauncher(installRoot, process.platform === 'win32', hermesHome)

  if (!launcher) {
    log(`No hermes launcher for ${installRoot} — skipping`)

    return false
  }

  try {
    const { stdout } = await execFileAsync(
      launcher,
      ['--run-module', 'hermes_cli.bifrost_edition'],
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
    log(`Bifrost setup failed: ${(err as Error).message}`)

    return false
  }

  return !needsBifrostStep(hermesHome)
}
