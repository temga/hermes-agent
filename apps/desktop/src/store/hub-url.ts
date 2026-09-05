/**
 * Skills Hub URL — resolves the base origin for the embedded hub picker
 * iframe and the backend skills index.
 *
 * The default (`https://hermes-agent.nousresearch.com`) is blocked by CDN
 * geofencing in some regions (e.g. Russia → Vercel/Fastly 403). The user
 * overrides it via `skills.hub_url` in config.yaml; an empty value keeps
 * the default.
 */
import { atom } from 'nanostores'

export const DEFAULT_HUB_ORIGIN = 'https://hermes-agent.nousresearch.com'

/** The resolved hub origin (no trailing slash). Updated by {@link resolveHubUrl}. */
export const $hubOrigin = atom<string>(DEFAULT_HUB_ORIGIN)

let fetched = false

/**
 * Fetch `skills.hub_url` from the gateway config. Called once on mount of
 * the first hub-picker component; the result is cached in `$hubOrigin` for
 * the session. Uses the provided `requestGateway` from `useGatewayRequest`.
 */
export async function resolveHubUrl(
  requestGateway: <T = unknown>(method: string, params?: Record<string, unknown>) => Promise<T>
): Promise<void> {
  if (fetched) {
    return
  }
  fetched = true
  try {
    const result = await requestGateway<{ value?: string }>('config.get', { key: 'skills.hub_url' })
    const override = result?.value?.trim()
    if (override) {
      $hubOrigin.set(override.replace(/\/+$/, ''))
    }
  } catch {
    // Config read failed — keep the default
  }
}

/** Build the picker iframe URL from the current origin. */
export function hubPickerUrl(): string {
  return $hubOrigin.get() + '/docs/skills?embed=picker'
}

/** The origin string to check against in postMessage handlers. */
export function hubOrigin(): string {
  return $hubOrigin.get()
}
