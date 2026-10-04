// @ts-check
'use strict'

// The macOS About panel prints CFBundleVersion in parentheses after the
// runtime version. Without an override it is package.json's version, which a
// Bifrost Edition checkout never bumps, so local builds named the release the
// app shell came from after a long-gone base. Name the nearest edition tag
// instead (same tag families as hermes_cli/version_info.py::_edition_release).

const { execFileSync } = require('node:child_process')

const EDITION_TAG = /^v(\d+\.\d+\.\d+-bifrost(?:-setup)?\.\d+)$/

/** @param {string | null | undefined} tag @returns {string | null} */
function editionVersionFromTag(tag) {
  return EDITION_TAG.exec((tag || '').trim())?.[1] ?? null
}

/** @param {string} repoRoot @returns {string | null} */
function nearestEditionVersion(repoRoot) {
  try {
    const tag = execFileSync(
      'git',
      ['describe', '--tags', '--abbrev=0', '--match', 'v*-bifrost.*', '--match', 'v*-bifrost-setup.*', 'HEAD'],
      { cwd: repoRoot, encoding: 'utf8', stdio: ['ignore', 'pipe', 'ignore'], timeout: 5000 }
    )
    return editionVersionFromTag(tag)
  } catch {
    // No git or no edition tag in history: keep electron-builder's default.
    return null
  }
}

module.exports = { editionVersionFromTag, nearestEditionVersion }
