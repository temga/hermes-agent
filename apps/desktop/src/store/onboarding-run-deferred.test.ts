import { beforeEach, expect, it, vi } from 'vitest'

import { setPrimaryGatewayConnectionId } from './gateway'
import { $desktopOnboarding } from './onboarding'
import { decideOnboarding, type OnboardingRequest } from './onboarding-run'
import { $connection, $selectedStoredSessionId } from './session'

// Its own file: decideOnboarding answers once per module, like once per launch.

beforeEach(() => {
  // SAFETY: factsSource reads only `mode`; a local connection skips the machine comparison.
  $connection.set({ mode: 'local' } as never)
  setPrimaryGatewayConnectionId('local')
  $selectedStoredSessionId.set(null)
})

it('starts a run that was due with nothing to carry it once a provider is connected', async () => {
  const state = { eligible: false, run: true, run_id: null as null | string, session_id: null as null | string }
  const calls: string[] = []

  const request = async <T>(method: string): Promise<T> => {
    calls.push(method)

    // SAFETY: the fake answers onboarding.state and onboarding.start with their contract result shapes.
    return (method === 'onboarding.state'
      ? state
      : { resumed: false, run_id: 'run-1', session_id: 'rt-1', stored_session_id: 'st-1' }) as T
  }

  const resume = vi.fn(async (storedId: string) => $selectedStoredSessionId.set(storedId))
  $desktopOnboarding.set({ ...$desktopOnboarding.get(), configured: false })

  await decideOnboarding(request as OnboardingRequest, resume, { ensureProfile: async () => undefined })
  expect(calls).toEqual(['onboarding.state'])

  Object.assign(state, { eligible: true, run_id: 'run-1', session_id: 'st-1' })
  $desktopOnboarding.set({ ...$desktopOnboarding.get(), configured: true })

  await vi.waitFor(() => expect(resume).toHaveBeenCalledWith('st-1', true))
  expect(calls).toContain('onboarding.start')
})
