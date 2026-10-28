// @vitest-environment node
import { afterEach, describe, expect, it, vi } from 'vitest'

import { fetchCatalog } from '@/app/capabilities/catalog/catalog-data'

import { resolveHubUrl } from './hub-url'

afterEach(() => {
  vi.unstubAllGlobals()
})

describe('skills.hub_url mirror', () => {
  it('sends catalog downloads to the configured mirror instead of the public host', async () => {
    const fetchMock = vi.fn(async () => new Response('[]'))
    vi.stubGlobal('fetch', fetchMock)

    const mirror = 'https://hub.example.test/'
    const requestGateway = vi.fn(async () => ({ value: `  ${mirror}  ` })) as never

    await resolveHubUrl(requestGateway)
    await fetchCatalog('skills')

    expect(fetchMock).toHaveBeenCalledWith('https://hub.example.test/docs/api/skills.json', expect.anything())
  })
})
