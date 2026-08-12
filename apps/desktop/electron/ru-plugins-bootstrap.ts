/**
 * ru-plugins-bootstrap.ts
 *
 * Bundled RU-ecosystem plugin installer for the Hermes desktop app.
 *
 * The desktop app ships the temga/hermes-ru-ecosystem plugins inside its
 * resources (apps/desktop/resources/ru-plugins/ → bundled at
 * process.resourcesPath/ru-plugins/ in a packaged build). On first launch
 * — or any launch where the plugins are missing from ~/.hermes/plugins/ —
 * this module copies them into the correct sub-category directories and
 * adds their names to plugins.enabled in config.yaml.
 *
 * Design choices:
 *
 * - **No YAML dependency.** The desktop app has no YAML parser in its dep
 *   tree. We manipulate plugins.enabled via targeted text edits (the section
 *   is a simple `- name` list). The rest of config.yaml is left untouched.
 *
 * - **Idempotent.** Running twice is a no-op: existing plugin directories
 *   are refreshed (rsync-style overwrite), and names already in
 *   plugins.enabled are not duplicated.
 *
 * - **Offline-capable.** No `hermes plugins install`, no git clone, no
 *   network. The plugin source is read from process.resourcesPath (packaged)
 *   or the source tree (dev).
 *
 * - **Non-fatal.** A failure logs a warning but never blocks app startup.
 *   The user can still use Hermes without the RU plugins; they just won't
 *   have the Russian ecosystem providers/platforms available.
 *
 * Plugin layout mirrors the Hermes PluginManager sub-category convention:
 *
 *   ~/.hermes/plugins/model-providers/<name>/   (kind: model-provider)
 *   ~/.hermes/plugins/platforms/<name>/         (kind: platform)
 *   ~/.hermes/plugins/backends/<name>/          (kind: backend)
 *
 * Because we copy into the sub-category directories directly, the
 * ProviderRegistry / PlatformManager / backend loaders discover them
 * without any symlink indirection.
 */

import fs from 'node:fs'
import fsp from 'node:fs/promises'
import path from 'node:path'
import { app } from 'electron'

/** A plugin entry in the bundled ru-plugins directory. */
interface RuPluginEntry {
  /** Sub-category under ~/.hermes/plugins/ (e.g. "model-providers"). */
  category: string
  /** Directory name within the category (e.g. "routerai"). */
  dirName: string
  /** Name to add to plugins.enabled in config.yaml. */
  enableName: string
}

/**
 * The bundled plugin manifest. Each entry maps a source directory inside
 * resources/ru-plugins/ to its destination sub-category under
 * ~/.hermes/plugins/ and the name Hermes expects in plugins.enabled.
 *
 * The enableName for sub-category plugins (model-providers, platforms,
 * backends) follows Hermes convention: "category/name". General plugins
 * use just the manifest name.
 */
const RU_PLUGINS: RuPluginEntry[] = [
  {
    category: 'model-providers',
    dirName: 'routerai',
    enableName: 'model-providers/routerai',
  },
  {
    category: 'model-providers',
    dirName: 'neuraldeep',
    enableName: 'model-providers/neuraldeep',
  },
  {
    category: 'platforms',
    dirName: 'max',
    enableName: 'platforms/max',
  },
  {
    category: 'backends',
    dirName: 'routerai-imagegen',
    enableName: 'backends/routerai-imagegen',
  },
  {
    category: 'backends',
    dirName: 'neuraldeep-search',
    enableName: 'backends/neuraldeep-search',
  },
]

/** Marker file written to ~/.hermes/ after a successful install. */
const STAMP_FILE = '.ru-plugins-installed'

/**
 * Resolve the bundled plugin source directory.
 *
 * In a packaged build this is process.resourcesPath/ru-plugins/.
 * In dev (electron-vite dev) it falls back to the source tree at
 * apps/desktop/resources/ru-plugins/.
 */
function resolveBundledPluginsDir(): string | null {
  // Packaged: resourcesPath points at the extraResources root.
  if (process.resourcesPath) {
    const bundled = path.join(process.resourcesPath, 'ru-plugins')
    if (fs.existsSync(path.join(bundled, 'model-providers'))) {
      return bundled
    }
  }

  // Dev fallback: source tree relative to the electron main directory.
  // apps/desktop/electron/ → apps/desktop/resources/ru-plugins
  const devPath = path.resolve(__dirname, '..', 'resources', 'ru-plugins')
  if (fs.existsSync(path.join(devPath, 'model-providers'))) {
    return devPath
  }

  // app.getAppPath() fallback (some dev configurations resolve __dirname
  // differently under electron-vite).
  try {
    const appPathFallback = path.resolve(app.getAppPath(), 'resources', 'ru-plugins')
    if (fs.existsSync(path.join(appPathFallback, 'model-providers'))) {
      return appPathFallback
    }
  } catch {
    // app may be undefined in tests
  }

  return null
}

/**
 * Recursively copy a directory, overwriting existing files. Creates the
 * destination if it doesn't exist. Uses fs.cpSync (Node 16.7+) for an
 * atomic recursive copy.
 */
function copyPluginDir(src: string, dest: string): void {
  fs.mkdirSync(dest, { recursive: true })
  // cpSync with force overwrite. filter excludes .git directories so
  // submodule metadata doesn't leak into ~/.hermes/plugins/.
  fs.cpSync(src, dest, {
    force: true,
    recursive: true,
    filter: (source) => {
      const base = path.basename(source)
      // Skip .git dirs and pycache at any depth.
      if (base === '.git' || base === '__pycache__') return false
      return true
    },
  })
}

/**
 * Read config.yaml and ensure all RU plugin names are in plugins.enabled.
 *
 * We do a targeted text edit rather than a full YAML parse+serialize:
 * the desktop app has no YAML dependency, and a round-trip through a
 * parser could reorder keys or change formatting in ways that surprise
 * the user. The plugins section looks like:
 *
 *   plugins:
 *     enabled:
 *       - existing-plugin
 *       - model-providers/routerai
 *     disabled: []
 *
 * Strategy: find the `plugins:` → `enabled:` block, parse the `- name`
 * lines, add any missing RU names, and rewrite just that block in place.
 * If there's no plugins section at all, append one.
 */
function ensurePluginsEnabled(configPath: string, names: string[]): void {
  let content = ''
  try {
    content = fs.readFileSync(configPath, 'utf-8')
  } catch {
    // No config.yaml yet — create a minimal one.
    const newContent = ['plugins:', '  enabled:', ...names.map((n) => `    - ${n}`), '  disabled: []', ''].join('\n')
    fs.mkdirSync(path.dirname(configPath), { recursive: true })
    fs.writeFileSync(configPath, newContent, 'utf-8')
    return
  }

  // Parse the plugins.enabled block via regex.
  // Matches: plugins:\n  enabled:\n    - name\n ...
  const pluginsSectionRe = /^plugins:\s*\n(\s+)enabled:\s*\n((?:\s+-\s+.*\n)*)/m
  const match = content.match(pluginsSectionRe)

  if (!match) {
    // No plugins.enabled section — append one at the end.
    const existingNames = new Set<string>()
    const toAdd = names.filter((n) => !existingNames.has(n))
    if (toAdd.length === 0) return

    const append = [
      '',
      'plugins:',
      '  enabled:',
      ...toAdd.map((n) => `    - ${n}`),
      '  disabled: []',
      '',
    ].join('\n')
    fs.writeFileSync(configPath, content.replace(/\n*$/, '\n') + append, 'utf-8')
    return
  }

  const indent = match[1] // the spaces before "enabled:"
  const enabledBlock = match[2] // the existing "- name\n" lines

  // Extract existing names from the block.
  const existingNames = new Set<string>()
  const lineRe = /^\s+-\s+(.+)$/gm
  let lm: RegExpExecArray | null
  while ((lm = lineRe.exec(enabledBlock)) !== null) {
    existingNames.add(lm[1].trim())
  }

  // Determine which names need to be added.
  const toAdd = names.filter((n) => !existingNames.has(n))
  if (toAdd.length === 0) return

  // Build the new enabled block: existing lines + new entries.
  const itemIndent = indent + '  '
  const newEntries = toAdd.map((n) => `${itemIndent}- ${n}`).join('\n')
  const newBlock = enabledBlock.replace(/\n*$/, '') + '\n' + newEntries + '\n'

  const newContent = content.replace(match[0], `plugins:\n${indent}enabled:\n${newBlock}`)
  fs.writeFileSync(configPath, newContent, 'utf-8')
}

/**
 * Check whether the RU plugins have already been installed to ~/.hermes.
 * Uses a stamp file plus a directory existence check for robustness.
 */
function isAlreadyInstalled(hermesHome: string): boolean {
  const stamp = path.join(hermesHome, STAMP_FILE)
  if (!fs.existsSync(stamp)) return false

  // Double-check at least one plugin dir actually exists — a stamp without
  // plugins means a partial/interrupted install.
  const pluginsDir = path.join(hermesHome, 'plugins')
  return RU_PLUGINS.some((p) => fs.existsSync(path.join(pluginsDir, p.category, p.dirName)))
}

/** Write the completion stamp. */
function writeStamp(hermesHome: string): void {
  try {
    fs.writeFileSync(
      path.join(hermesHome, STAMP_FILE),
      JSON.stringify({ installedAt: new Date().toISOString(), count: RU_PLUGINS.length }),
      'utf-8',
    )
  } catch {
    // Non-fatal — next launch will re-verify via directory check.
  }
}

/**
 * Install bundled RU plugins into ~/.hermes/plugins/ and enable them in
 * config.yaml. Safe to call on every launch — it's a no-op once the
 * stamp file exists and plugins are in place.
 *
 * @param hermesHome  The resolved HERMES_HOME directory.
 * @param log         Optional logger (defaults to console.warn).
 * @returns true if plugins were installed or already present, false on error.
 */
export async function ensureRuPlugins(
  hermesHome: string,
  log: (msg: string) => void = (m) => console.warn(`[ru-plugins] ${m}`),
): Promise<boolean> {
  // Resolve the bundled source.
  const bundledDir = resolveBundledPluginsDir()
  if (!bundledDir) {
    log('Bundled RU plugins directory not found — skipping (dev build without resources?)')
    return false
  }

  // Fast path: already installed.
  if (isAlreadyInstalled(hermesHome)) {
    return true
  }

  log(`Installing bundled RU plugins from ${bundledDir} → ${hermesHome}/plugins/`)

  try {
    const pluginsDir = path.join(hermesHome, 'plugins')
    fs.mkdirSync(pluginsDir, { recursive: true })

    let installed = 0
    for (const plugin of RU_PLUGINS) {
      const src = path.join(bundledDir, plugin.category, plugin.dirName)
      const dest = path.join(pluginsDir, plugin.category, plugin.dirName)

      if (!fs.existsSync(src)) {
        log(`Source missing for ${plugin.enableName} (${src}) — skipping`)
        continue
      }

      try {
        copyPluginDir(src, dest)
        installed++
      } catch (err) {
        log(`Failed to copy ${plugin.enableName}: ${(err as Error).message}`)
      }
    }

    if (installed === 0) {
      log('No plugins were copied — aborting config update')
      return false
    }

    // Enable in config.yaml.
    const configPath = path.join(hermesHome, 'config.yaml')
    const enableNames = RU_PLUGINS.map((p) => p.enableName)
    try {
      ensurePluginsEnabled(configPath, enableNames)
      log(`Enabled ${installed} RU plugins in config.yaml`)
    } catch (err) {
      log(`Failed to update config.yaml: ${(err as Error).message} — plugins copied but not enabled`)
    }

    writeStamp(hermesHome)
    log(`RU plugins installed (${installed}/${RU_PLUGINS.length})`)
    return true
  } catch (err) {
    log(`RU plugin installation failed: ${(err as Error).message}`)
    return false
  }
}

/**
 * Force re-install — clears the stamp and re-copies. Exposed for a future
 * "Repair RU plugins" button in Settings. Not wired into the UI yet.
 */
export async function reinstallRuPlugins(
  hermesHome: string,
  log?: (msg: string) => void,
): Promise<boolean> {
  const stamp = path.join(hermesHome, STAMP_FILE)
  try {
    fs.unlinkSync(stamp)
  } catch {
    // ignore — may not exist
  }
  return ensureRuPlugins(hermesHome, log)
}
