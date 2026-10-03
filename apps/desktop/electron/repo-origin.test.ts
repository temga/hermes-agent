import { describe, expect, it } from 'vitest'

import { repoOriginUrl } from './repo-origin'

describe('repoOriginUrl', () => {
  it('canonicalizes GitHub SSH and HTTPS remotes', () => {
    expect(repoOriginUrl('git@github.com:temga/hermes-agent.git')).toBe('https://github.com/temga/hermes-agent')
    expect(repoOriginUrl('https://github.com/temga/hermes-agent.git')).toBe('https://github.com/temga/hermes-agent')
    expect(repoOriginUrl('ssh://git@github.com/NousResearch/hermes-agent')).toBe(
      'https://github.com/NousResearch/hermes-agent'
    )
  })

  it('returns null for non-GitHub or empty remotes', () => {
    expect(repoOriginUrl('https://gitlab.com/a/b.git')).toBeNull()
    expect(repoOriginUrl('')).toBeNull()
    expect(repoOriginUrl(undefined)).toBeNull()
  })
})
