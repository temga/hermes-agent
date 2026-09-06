import { useState } from 'react'

import { Button } from '@/components/ui/button'
import { type Locale, LOCALE_OPTIONS, useI18n } from '@/i18n'
import { Check } from '@/lib/icons'
import { cn } from '@/lib/utils'

/**
 * First-run language picker shown before the provider onboarding step.
 * Pre-selects the current locale (default 'ru' for the Bifrost edition) and
 * lets the user confirm or switch before proceeding to provider setup.
 *
 * The choice is persisted via `setLocale` (same path as Settings → Language),
 * so it survives across sessions. In manual mode (re-opened from Settings)
 * this step is skipped — the user already has a language.
 */
export function LanguageStep({ onContinue }: { onContinue: () => void }) {
  const { locale, setLocale, t } = useI18n()
  const [selected, setSelected] = useState<Locale>(locale)
  const [saving, setSaving] = useState(false)

  const confirm = async () => {
    if (selected === locale) {
      onContinue()
      return
    }

    setSaving(true)
    try {
      await setLocale(selected)
      onContinue()
    } catch {
      // setLocale surfaces its own error in the provider; stay on this step
    } finally {
      setSaving(false)
    }
  }

  return (
    <div className="grid gap-4">
      <div>
        <h3 className="text-sm font-semibold">{t.onboarding.chooseLanguageTitle}</h3>
        <p className="mt-1 text-xs leading-5 text-muted-foreground">{t.onboarding.chooseLanguageDesc}</p>
      </div>

      <div className="grid max-h-[48dvh] gap-2 overflow-y-auto p-1 sm:grid-cols-2">
        {LOCALE_OPTIONS.map(opt => {
          const isSelected = opt.id === selected

          return (
            <button
              className={cn(
                'rounded-2xl border bg-background/60 p-3 text-left transition hover:bg-accent/50',
                isSelected ? 'border-primary ring-2 ring-primary/20' : 'border-transparent'
              )}
              key={opt.id}
              onClick={() => setSelected(opt.id)}
              type="button"
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-sm font-medium">{opt.name}</span>
                {isSelected ? <Check className="size-3.5 text-muted-foreground" /> : null}
              </div>
              <p className="mt-1 text-xs text-muted-foreground">{opt.englishName}</p>
            </button>
          )
        })}
      </div>

      <div className="flex justify-end">
        <Button disabled={saving} onClick={() => void confirm()}>
          {t.common.continue}
        </Button>
      </div>
    </div>
  )
}
