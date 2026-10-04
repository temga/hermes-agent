import { useStore } from '@nanostores/react'
import { useEffect, useLayoutEffect } from 'react'

import { endChatOnboardingSolo, takeGuideShape } from '@/components/onboarding-chat/assembly'
import { isOnboardingEnabled } from '@/lib/onboarding-enabled'
import { ackFreeTierNotice, type FreeTierRequester } from '@/store/free-tier'
import { $desktopOnboarding, clearFreeTierIntro } from '@/store/onboarding'
import {
  $guideOpening,
  $onboardingGate,
  beginOnboardingFlow,
  requeueDeferredGuide,
  runGuideKickoff,
  skipGuide
} from '@/store/onboarding-gate'

import { GuideLoading } from './guide-loading'

interface OnboardingChatGateProps {
  enabled: boolean
  onKickoff: () => Promise<boolean>
  requestGateway: FreeTierRequester
}

export function OnboardingChatGate({ enabled, onKickoff, requestGateway }: OnboardingChatGateProps) {
  const gate = useStore($onboardingGate)
  const opening = useStore($guideOpening)

  useLayoutEffect(() => {
    beginOnboardingFlow($desktopOnboarding.get().firstRunSkipped)

    if ($onboardingGate.get().guideQueued) {
      takeGuideShape()
    }
  }, [])

  useEffect(() => {
    if (!enabled || !isOnboardingEnabled()) {
      return
    }

    const ack = () => {
      clearFreeTierIntro()
      void ackFreeTierNotice(requestGateway).then(acked => {
        if (acked) {
          clearFreeTierIntro()
        }
      })
    }

    return $onboardingGate.subscribe(state => {
      if (state.phase === 'guided') {
        ack()
      }
    })
  }, [enabled, requestGateway])

  useEffect(() => {
    if (!isOnboardingEnabled()) {
      return
    }

    // Only a transition to configured counts: the store replays its current
    // value on subscribe, and a stale `configured` the guide's own readiness
    // check disagreed with would otherwise requeue it in a loop.
    let wasConfigured = $desktopOnboarding.get().configured === true

    return $desktopOnboarding.subscribe(({ configured }) => {
      const nowConfigured = configured === true

      if (nowConfigured && !wasConfigured && requeueDeferredGuide()) {
        takeGuideShape()
      }

      wasConfigured = nowConfigured
    })
  }, [])

  useEffect(() => {
    if (enabled && gate.guideQueued) {
      const recover = () => {
        endChatOnboardingSolo()
        skipGuide()
      }

      void runGuideKickoff(onKickoff).then(started => {
        if (!started) {
          recover()
        }
      }, recover)
    }
  }, [enabled, gate.guideQueued, onKickoff])

  return opening ? <GuideLoading /> : null
}
