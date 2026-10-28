/**
 * Skills Hub mirror — `skills.hub_url` in config.yaml.
 *
 * The public catalog host is unreachable in some regions (e.g. Russia → CDN
 * geofencing 403). `skills.hub_url` names a mirror origin of the docs site;
 * the catalog then reads its JSON snapshots from `<origin>/docs/api/`. An
 * empty value keeps the public catalog.
 */
import { atom } from 'nanostores'

import { queryClient } from '@/lib/query-client'

/** The configured mirror origin (no trailing slash), or null for the public catalog. */
export const $hubOrigin = atom<string | null>(null)

let resolved = false

/**
 * Read `skills.hub_url` from the gateway config once per app session. A new
 * origin drops any catalog fetched from the public host before the config
 * arrived, so the next read goes to the mirror. A failed read (gateway not
 * up yet) is retried on the next call.
 */
export async function resolveHubUrl(
  requestGateway: <T = unknown>(method: string, params?: Record<string, unknown>) => Promise<T>
): Promise<void> {
  if (resolved) {
    return
  }

  let override: string | undefined

  try {
    const result = await requestGateway<{ value?: string }>('config.get', { key: 'skills.hub_url' })
    override = result?.value?.trim()
    resolved = true
  } catch {
    return
  }

  if (!override) {
    return
  }

  $hubOrigin.set(override.replace(/\/+$/, ''))
  void queryClient.resetQueries({ queryKey: ['public-catalog'] })
}

/** The mirror's catalog API base, or null when no mirror is configured. */
export function hubCatalogBase(): string | null {
  const origin = $hubOrigin.get()

  return origin ? `${origin}/docs/api` : null
}
