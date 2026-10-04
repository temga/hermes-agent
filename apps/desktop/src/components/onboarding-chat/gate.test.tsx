import { cleanup, render, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import type * as OnboardingStore from '@/store/onboarding'
import type * as GateStore from '@/store/onboarding-gate'

import type * as Gate from './gate'

// The guide's kickoff and deferral live in module state, so each case gets
// fresh modules.
let OnboardingChatGate: typeof Gate.OnboardingChatGate
let $onboardingGate: typeof GateStore.$onboardingGate
let deferGuideUntilProvider: typeof GateStore.deferGuideUntilProvider
let $desktopOnboarding: typeof OnboardingStore.$desktopOnboarding

vi.mock('@/components/onboarding-chat/assembly', () => ({
  endChatOnboardingSolo: vi.fn(),
  takeGuideShape: vi.fn()
}))

const requestGateway = vi.fn(async () => ({})) as never

function setConfigured(configured: boolean | null): void {
  $desktopOnboarding.set({ ...$desktopOnboarding.get(), configured, firstRunSkipped: false })
}

beforeEach(async () => {
  vi.resetModules()
  ;({ OnboardingChatGate } = await import('./gate'))
  ;({ $onboardingGate, deferGuideUntilProvider } = await import('@/store/onboarding-gate'))
  ;({ $desktopOnboarding } = await import('@/store/onboarding'))
  window.hermesDesktop = { ...window.hermesDesktop, guestOnboardingEnabled: true } as typeof window.hermesDesktop
  window.localStorage.clear()
  $onboardingGate.set({ phase: 'idle', guideQueued: false, guideKickoff: 'idle' })
  setConfigured(false)
})

afterEach(() => {
  cleanup()
  window.localStorage.clear()
})

// A first launch with no free tier has no provider until the user connects one
// in onboarding. The guide must wait for it, not be lost to it.
describe('OnboardingChatGate without a provider yet', () => {
  it('starts the guide once a provider is connected instead of recording it as skipped', async () => {
    const onKickoff = vi
      .fn<() => Promise<boolean>>()
      .mockImplementationOnce(async () => {
        deferGuideUntilProvider()

        return false
      })
      .mockResolvedValue(true)

    render(<OnboardingChatGate enabled onKickoff={onKickoff} requestGateway={requestGateway} />)

    await waitFor(() => expect(onKickoff).toHaveBeenCalledTimes(1))
    await waitFor(() => expect($onboardingGate.get().phase).toBe('idle'))

    setConfigured(true)

    await waitFor(() => expect(onKickoff).toHaveBeenCalledTimes(2))
    await waitFor(() => expect($onboardingGate.get().phase).toBe('guided'))
  })

  it('does not retry a deferred guide while the app is already configured', async () => {
    setConfigured(true)

    const onKickoff = vi.fn(async () => {
      deferGuideUntilProvider()

      return false
    })

    render(<OnboardingChatGate enabled onKickoff={onKickoff} requestGateway={requestGateway} />)

    await waitFor(() => expect(onKickoff).toHaveBeenCalledTimes(1))
    setConfigured(true)
    await new Promise(resolve => setTimeout(resolve, 50))

    expect(onKickoff).toHaveBeenCalledTimes(1)
    expect($onboardingGate.get().phase).toBe('idle')
  })
})
