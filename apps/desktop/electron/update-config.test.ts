import assert from 'node:assert/strict'
import fs from 'node:fs'
import os from 'node:os'
import path from 'node:path'

import { test } from 'vitest'

import {
  DEFAULT_UPDATE_BRANCH,
  readConfiguredUpdateBranch,
  readDesktopUpdateConfig,
} from './update-config'

function tmpFile(content: string, ext = '.yaml'): string {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), 'update-config-test-'))
  const file = path.join(dir, `config${ext}`)
  fs.writeFileSync(file, content, 'utf-8')
  return file
}

function tmpDir(): string {
  return fs.mkdtempSync(path.join(os.tmpdir(), 'update-config-test-'))
}

// ── readConfiguredUpdateBranch ──────────────────────────────────────────────

test('reads updates.branch from config.yaml', () => {
  const p = tmpFile('updates:\n  branch: bifrost-edition\n')
  assert.equal(readConfiguredUpdateBranch(p), 'bifrost-edition')
})

test('returns default when updates.branch is absent', () => {
  const p = tmpFile('updates:\n  pre_update_backup: quick\n')
  assert.equal(readConfiguredUpdateBranch(p), DEFAULT_UPDATE_BRANCH)
})

test('returns default when updates section is absent', () => {
  const p = tmpFile('model:\n  provider: bifrost\n')
  assert.equal(readConfiguredUpdateBranch(p), DEFAULT_UPDATE_BRANCH)
})

test('returns default when config.yaml does not exist', () => {
  assert.equal(readConfiguredUpdateBranch('/nonexistent/config.yaml'), DEFAULT_UPDATE_BRANCH)
})

test('tolerates 4-space indent', () => {
  const p = tmpFile('updates:\n    branch: custom-branch\n')
  assert.equal(readConfiguredUpdateBranch(p), 'custom-branch')
})

test('strips inline comments after the branch value', () => {
  const p = tmpFile('updates:\n  branch: my-branch  # fork tracking\n')
  assert.equal(readConfiguredUpdateBranch(p), 'my-branch')
})

test('honours a custom fallback', () => {
  const p = tmpFile('model:\n  provider: bifrost\n')
  assert.equal(readConfiguredUpdateBranch(p, 'custom-default'), 'custom-default')
})

// ── readDesktopUpdateConfig (priority chain) ────────────────────────────────

test('updates.json wins over config.yaml', () => {
  const jsonDir = tmpDir()
  const jsonPath = path.join(jsonDir, 'updates.json')
  fs.writeFileSync(jsonPath, JSON.stringify({ branch: 'gui-override' }), 'utf-8')

  const yamlPath = tmpFile('updates:\n  branch: bifrost-edition\n')

  assert.deepEqual(
    readDesktopUpdateConfig(jsonPath, yamlPath),
    { branch: 'gui-override' },
  )
})

test('falls back to config.yaml when updates.json has no branch', () => {
  const jsonDir = tmpDir()
  const jsonPath = path.join(jsonDir, 'updates.json')
  fs.writeFileSync(jsonPath, JSON.stringify({}), 'utf-8')

  const yamlPath = tmpFile('updates:\n  branch: bifrost-edition\n')

  assert.deepEqual(
    readDesktopUpdateConfig(jsonPath, yamlPath),
    { branch: 'bifrost-edition' },
  )
})

test('falls back to config.yaml when updates.json is absent', () => {
  const yamlPath = tmpFile('updates:\n  branch: bifrost-edition\n')

  assert.deepEqual(
    readDesktopUpdateConfig('/nonexistent/updates.json', yamlPath),
    { branch: 'bifrost-edition' },
  )
})

test('falls back to default when both updates.json and config.yaml are absent', () => {
  assert.deepEqual(
    readDesktopUpdateConfig('/nonexistent/updates.json', '/nonexistent/config.yaml'),
    { branch: DEFAULT_UPDATE_BRANCH },
  )
})

test('falls back to default when updates.json is absent and config.yaml has no updates.branch', () => {
  const yamlPath = tmpFile('model:\n  provider: bifrost\n')

  assert.deepEqual(
    readDesktopUpdateConfig('/nonexistent/updates.json', yamlPath),
    { branch: DEFAULT_UPDATE_BRANCH },
  )
})

test('empty string in updates.json falls through to config.yaml', () => {
  const jsonDir = tmpDir()
  const jsonPath = path.join(jsonDir, 'updates.json')
  fs.writeFileSync(jsonPath, JSON.stringify({ branch: '' }), 'utf-8')

  const yamlPath = tmpFile('updates:\n  branch: bifrost-edition\n')

  assert.deepEqual(
    readDesktopUpdateConfig(jsonPath, yamlPath),
    { branch: 'bifrost-edition' },
  )
})
