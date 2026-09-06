/**
 * update-config.ts
 *
 * Pure, dependency-injected pieces of the desktop self-update branch
 * resolution, pulled out of main.ts so they can be unit-tested without
 * mocking Electron.
 *
 * Branch priority (highest wins):
 *   1. updates.json (GUI override — user clicked "switch branch")
 *   2. config.yaml  (updates.branch — fork/custom deployment default)
 *   3. "main"       (upstream default)
 *
 * config.yaml is parsed with a regex (no js-yaml dependency in the
 * electron main process), matching the same approach used by
 * ru-plugins-bootstrap.ts / bifrost-plugins-bootstrap.ts.
 */

import fs from 'node:fs'
import path from 'node:path'

export const DEFAULT_UPDATE_BRANCH = 'main'

/**
 * Read ``updates.branch`` from a config.yaml file.
 *
 * Returns the trimmed branch string, or ``DEFAULT_UPDATE_BRANCH`` when
 * the key is absent / the file can't be read.
 */
export function readConfiguredUpdateBranch(
  configYamlPath: string,
  fallback: string = DEFAULT_UPDATE_BRANCH,
): string {
  try {
    const content = fs.readFileSync(configYamlPath, 'utf-8')
    // Match: updates:\n  branch: <value>
    // Tolerates any indent depth (2 or 4 spaces) and inline comments.
    const m = content.match(/^updates:\s*\n(?:[ \t]*branch:\s*)([^\s#]+)/m)
    if (m && m[1]) {
      const branch = m[1].trim()
      if (branch) return branch
    }
  } catch {
    // No config.yaml or unreadable — fall through to default.
  }
  return fallback
}

/**
 * Read the desktop update config, falling back to config.yaml when the
 * GUI override (updates.json) is absent or empty.
 *
 * @param updatesJsonPath  Path to updates.json (Electron userData)
 * @param configYamlPath   Path to config.yaml (HERMES_HOME)
 */
export function readDesktopUpdateConfig(
  updatesJsonPath: string,
  configYamlPath: string,
): { branch: string } {
  // Priority: updates.json (GUI override) > config.yaml (updates.branch) > DEFAULT_UPDATE_BRANCH
  try {
    const parsed = JSON.parse(fs.readFileSync(updatesJsonPath, 'utf8'))
    const branch = typeof parsed?.branch === 'string' ? parsed.branch.trim() : ''

    if (branch) return { branch }
  } catch {
    // No updates.json — fall through to config.yaml.
  }
  return { branch: readConfiguredUpdateBranch(configYamlPath) }
}
