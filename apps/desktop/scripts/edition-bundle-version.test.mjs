import { describe, expect, it } from 'vitest'
import { createRequire } from 'node:module'

const require = createRequire(import.meta.url)
const { editionVersionFromTag } = require('./edition-bundle-version.cjs')

describe('editionVersionFromTag', () => {
  it('names the edition release both tag families shipped', () => {
    expect(editionVersionFromTag('v0.21.5-bifrost.6\n')).toBe('0.21.5-bifrost.6')
    expect(editionVersionFromTag('v0.21.4-bifrost-setup.5')).toBe('0.21.4-bifrost-setup.5')
  })

  it('leaves non-edition tags to the default bundle version', () => {
    for (const tag of ['v2026.9.24', 'v0.21.0', '', null, 'v0.21.5-bifrost.6-1-gdf7e8f6']) {
      expect(editionVersionFromTag(tag)).toBeNull()
    }
  })
})
