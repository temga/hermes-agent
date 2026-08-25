/**
 * bifrost-plugins-bootstrap.ts
 *
 * Bundled Bifrost Gateway plugin installer for the Hermes desktop app.
 *
 * The desktop app ships the temga/hermes-plugin-bifrost-gateway plugins inside
 * its resources (apps/desktop/resources/bifrost-plugins/ → bundled at
 * process.resourcesPath/bifrost-plugins/ in a packaged build). On first launch
 * — or any launch where the plugins are missing from ~/.hermes/plugins/ —
 * this module copies them into the correct sub-category directories and
 * adds their names to plugins.enabled in config.yaml.
 *
 * Mirrors ru-plugins-bootstrap.ts but for the Bifrost ecosystem:
 * 5 plugins across 5 categories (model-providers, image_gen, web,
 * transcription, tts), all powered by a single BIFROST_API_KEY (sk-bf-*).
 *
 * Design choices (same as ru-plugins-bootstrap):
 *
 * - **No YAML dependency.** Targeted text edits, no YAML round-trip.
 * - **Idempotent.** Running twice is a no-op.
 * - **Offline-capable.** No network — reads from process.resourcesPath.
 * - **Non-fatal.** A failure logs a warning but never blocks app startup.
 */

import fs from 'node:fs'
import path from 'node:path'
import { fileURLToPath } from 'node:url'
import { execFileSync } from 'node:child_process'

import { app } from 'electron'

// ESM-safe __dirname (same fix as ru-plugins-bootstrap).
const __dirname = path.dirname(fileURLToPath(import.meta.url))

/** A plugin entry in the bundled bifrost-plugins directory. */
interface BifrostPluginEntry {
  /** Sub-category under ~/.hermes/plugins/ (e.g. "model-providers"). */
  category: string
  /** Directory name within the category (e.g. "bifrost"). */
  dirName: string
  /** Name to add to plugins.enabled in config.yaml. */
  enableName: string
}

/**
 * The bundled plugin manifest. 5 plugins, 5 categories — all share one key.
 * Categories mirror hermes-plugin-bifrost-gateway/install.sh.
 */
const BIFROST_PLUGINS: BifrostPluginEntry[] = [
  {
    category: 'model-providers',
    dirName: 'bifrost',
    enableName: 'model-providers/bifrost',
  },
  {
    category: 'image_gen',
    dirName: 'bifrost',
    enableName: 'image_gen/bifrost',
  },
  {
    category: 'web',
    dirName: 'bifrost',
    enableName: 'web/bifrost',
  },
  {
    category: 'transcription',
    dirName: 'bifrost',
    enableName: 'transcription/bifrost',
  },
  {
    category: 'tts',
    dirName: 'bifrost',
    enableName: 'tts/bifrost',
  },
]

/** Marker file written to ~/.hermes/ after a successful install. */
const STAMP_FILE = '.bifrost-plugins-installed'

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

/** Recursively copy, overwriting existing. Excludes .git/__pycache__. */
function copyPluginDir(src: string, dest: string): void {
  fs.mkdirSync(dest, { recursive: true })
  fs.cpSync(src, dest, {
    force: true,
    recursive: true,
    filter: (source) => {
      const base = path.basename(source)

      if (base === '.git' || base === '__pycache__') {
        return false
      }

      return true
    },
  })
}

/**
 * Read config.yaml and ensure all Bifrost plugin names are in plugins.enabled.
 * Same targeted-text-edit strategy as ru-plugins-bootstrap.
 */
function ensurePluginsEnabled(configPath: string, names: string[]): void {
  let content = ''

  try {
    content = fs.readFileSync(configPath, 'utf-8')
  } catch {
    const newContent = ['plugins:', '  enabled:', ...names.map((n) => `    - ${n}`), '  disabled: []', ''].join('\n')
    fs.mkdirSync(path.dirname(configPath), { recursive: true })
    fs.writeFileSync(configPath, newContent, 'utf-8')

    return
  }

  const pluginsSectionRe = /^plugins:\s*\n(\s+)enabled:\s*\n((?:\s+-\s+.*\n)*)/m
  const match = content.match(pluginsSectionRe)

  if (!match) {
    const existingNames = new Set<string>()
    const toAdd = names.filter((n) => !existingNames.has(n))

    if (toAdd.length === 0) {
      return
    }

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

  const indent = match[1]
  const enabledBlock = match[2]

  const existingNames = new Set<string>()
  const lineRe = /^\s+-\s+(.+)$/gm
  let lm: RegExpExecArray | null

  while ((lm = lineRe.exec(enabledBlock)) !== null) {
    existingNames.add(lm[1].trim())
  }

  const toAdd = names.filter((n) => !existingNames.has(n))

  if (toAdd.length === 0) {
    return
  }

  const itemIndent = indent + '  '
  const newEntries = toAdd.map((n) => `${itemIndent}- ${n}`).join('\n')
  const newBlock = enabledBlock.replace(/\n*$/, '') + '\n' + newEntries + '\n'

  const newContent = content.replace(match[0], `plugins:\n${indent}enabled:\n${newBlock}`)
  fs.writeFileSync(configPath, newContent, 'utf-8')
}

/** Check whether plugins have already been installed. */
function isAlreadyInstalled(hermesHome: string): boolean {
  const stamp = path.join(hermesHome, STAMP_FILE)

  if (fs.existsSync(stamp)) {
    const pluginsDir = path.join(hermesHome, 'plugins')

    if (BIFROST_PLUGINS.some((p) => fs.existsSync(path.join(pluginsDir, p.category, p.dirName)))) {
      return true
    }
  }

  return false
}

/** Write the completion stamp. */
function writeStamp(hermesHome: string): void {
  try {
    fs.writeFileSync(
      path.join(hermesHome, STAMP_FILE),
      JSON.stringify({ installedAt: new Date().toISOString(), count: BIFROST_PLUGINS.length }),
      'utf-8',
    )
  } catch {
    // Non-fatal
  }
}

/**
 * Configure all service providers to use Bifrost in config.yaml.
 * Mirrors install_bifrost_plugins() in scripts/install.sh:
 *   model.provider, model.default, model.base_url
 *   image_gen.provider
 *   web.search_backend, web.extract_backend
 *   stt.provider, stt.bifrost.model, stt.bifrost.language
 *   tts.provider, tts.bifrost.model
 *
 * Uses the venv Python (available at this point in startup) to do a proper
 * YAML-aware edit via hermes_cli.config — no fragile text regex.
 * Non-fatal: a failure logs but never blocks startup.
 */
function configureServiceProviders(hermesHome: string, log: (msg: string) => void): void {
  const configPath = path.join(hermesHome, 'config.yaml')
  if (!fs.existsSync(configPath)) {
    log('config.yaml not found — skipping service provider configuration')

    return
  }

  // Resolve venv Python. VENV_ROOT is <hermesHome>/hermes-agent/venv — same
  // path main.ts uses (ACTIVE_HERMES_ROOT / VENV_ROOT). We resolve it here
  // to avoid importing Electron-specific constants that aren't available
  // in the test environment.
  const hermesRoot = path.join(hermesHome, 'hermes-agent')
  const venvPython = process.platform === 'win32'
    ? path.join(hermesRoot, 'venv', 'Scripts', 'python.exe')
    : path.join(hermesRoot, 'venv', 'bin', 'python')

  if (!fs.existsSync(venvPython)) {
    log(`venv Python not found at ${venvPython} — skipping service provider configuration`)

    return
  }

  const script = `
import sys
from hermes_cli.config import load_config, save_config

cfg = load_config()

# model: provider + default + base_url
# base_url MUST point at the Bifrost gateway — the template's openrouter.ai
# URL is stale and produces 403 at runtime.
model = cfg.setdefault('model', {})
model['provider'] = 'bifrost'
model['default'] = 'neuraldeep/gpt-oss-120b'
model['base_url'] = 'https://router.rove-ai.ru/v1'

# image_gen: provider
img = cfg.setdefault('image_gen', {})
img['provider'] = 'bifrost'

# web: search + extract backends
web = cfg.setdefault('web', {})
web['search_backend'] = 'bifrost'
web['extract_backend'] = 'bifrost'

# stt: provider + bifrost config (language: ru is critical)
stt = cfg.setdefault('stt', {})
stt['provider'] = 'bifrost'
stt_bf = stt.setdefault('bifrost', {})
stt_bf['model'] = 'neuraldeep/whisper-podlodka-turbo'
stt_bf['language'] = 'ru'

# tts: provider + bifrost config
tts = cfg.setdefault('tts', {})
tts['provider'] = 'bifrost'
tts_bf = tts.setdefault('bifrost', {})
tts_bf['model'] = 'espeech-tts'

save_config(cfg, merge_existing=True)
print("Configured all service providers → bifrost")
`

  try {
    const output = execFileSync(venvPython, ['-c', script], {
      cwd: hermesRoot,
      timeout: 15000,
      encoding: 'utf-8',
      stdio: ['pipe', 'pipe', 'pipe'],
    })
    log(output.trim() || 'Service providers configured → bifrost')
  } catch (err) {
    log(`Failed to configure service providers: ${(err as Error).message}`)
  }
}

/**
 * Install bundled Bifrost plugins into ~/.hermes/plugins/ and enable them in
 * config.yaml. Safe to call on every launch — no-op once stamp exists.
 */
export async function ensureBifrostPlugins(
  hermesHome: string,
  log: (msg: string) => void = (m) => console.warn(`[bifrost-plugins] ${m}`),
): Promise<boolean> {
  const bundledDir = resolveBundledPluginsDir()

  if (!bundledDir) {
    log('Bundled Bifrost plugins directory not found — skipping (dev build without resources?)')

    return false
  }

  if (isAlreadyInstalled(hermesHome)) {
    return true
  }

  log(`Installing bundled Bifrost plugins from ${bundledDir} → ${hermesHome}/plugins/`)

  try {
    const pluginsDir = path.join(hermesHome, 'plugins')
    fs.mkdirSync(pluginsDir, { recursive: true })

    let installed = 0

    for (const plugin of BIFROST_PLUGINS) {
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

    const configPath = path.join(hermesHome, 'config.yaml')
    const enableNames = BIFROST_PLUGINS.map((p) => p.enableName)

    try {
      ensurePluginsEnabled(configPath, enableNames)
      log(`Enabled ${installed} Bifrost plugins in config.yaml`)
    } catch (err) {
      log(`Failed to update config.yaml: ${(err as Error).message} — plugins copied but not enabled`)
    }

    // Configure all service providers (model, image_gen, web, stt, tts) to
    // use Bifrost. Without this, the template's openrouter.ai base_url stays
    // in config.yaml and LLM requests fail with 403. Mirrors
    // install_bifrost_plugins() in scripts/install.sh.
    try {
      configureServiceProviders(hermesHome, log)
    } catch (err) {
      log(`Failed to configure service providers: ${(err as Error).message}`)
    }

    writeStamp(hermesHome)
    log(`Bifrost plugins installed (${installed}/${BIFROST_PLUGINS.length})`)

    return true
  } catch (err) {
    log(`Bifrost plugin installation failed: ${(err as Error).message}`)

    return false
  }
}

/** Force re-install — clears the stamp and re-copies. */
export async function reinstallBifrostPlugins(
  hermesHome: string,
  log?: (msg: string) => void,
): Promise<boolean> {
  const stamp = path.join(hermesHome, STAMP_FILE)

  try {
    fs.unlinkSync(stamp)
  } catch {
    // ignore
  }

  return ensureBifrostPlugins(hermesHome, log)
}
