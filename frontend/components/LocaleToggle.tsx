'use client'

import { LocaleId, LocaleInfo } from '@/types'

interface LocaleToggleProps {
  value: LocaleId
  locales: LocaleInfo[]
  onChange: (locale: LocaleId) => void
  disabled?: boolean
}

// Light presentation metadata; anything not listed falls back to a neutral chip.
const LOCALE_UI: Record<string, { flag: string; short: string; sub: string }> = {
  us_armd: { flag: '🇺🇸', short: 'United States', sub: 'RandomForest · ARMD' },
  pakistan: { flag: '🇵🇰', short: 'Pakistan', sub: 'Local antibiogram · Route A' },
}

export default function LocaleToggle({ value, locales, onChange, disabled }: LocaleToggleProps) {
  return (
    <div className="mx-auto mb-8 max-w-3xl">
      <div className="rounded-2xl border border-slate-200 bg-white/70 p-1.5 shadow-sm backdrop-blur">
        <div className="grid grid-cols-2 gap-1.5">
          {locales.map((loc) => {
            const ui = LOCALE_UI[loc.id] ?? { flag: '🌐', short: loc.display_name, sub: loc.basis }
            const active = loc.id === value
            return (
              <button
                key={loc.id}
                type="button"
                disabled={disabled}
                onClick={() => onChange(loc.id)}
                aria-pressed={active}
                className={`flex items-center justify-center gap-3 rounded-xl px-4 py-3 text-left transition-all disabled:cursor-not-allowed disabled:opacity-60 ${
                  active
                    ? 'bg-gradient-to-r from-blue-600 to-indigo-600 text-white shadow-md'
                    : 'text-slate-600 hover:bg-slate-100'
                }`}
              >
                <span className="text-2xl leading-none">{ui.flag}</span>
                <span className="flex flex-col">
                  <span className="text-sm font-semibold leading-tight">{ui.short}</span>
                  <span className={`text-xs leading-tight ${active ? 'text-blue-100' : 'text-slate-400'}`}>
                    {ui.sub}
                  </span>
                </span>
              </button>
            )
          })}
        </div>
      </div>
      <p className="mt-2 text-center text-xs text-slate-500">
        Recommendation locale — the same case can yield different first-line drugs where local resistance differs.
      </p>
    </div>
  )
}
