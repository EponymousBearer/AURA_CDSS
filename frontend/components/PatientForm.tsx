'use client'

import { useEffect, useMemo, useState } from 'react'
import { ARMDFormProps, ARMDFormData, WardType } from '@/types'
import { getARMDOrganismCatalog } from '@/services/api'

type OrganismChoice = { value: string; label: string; disabled: boolean }

const FALLBACK_ORGANISMS_BY_CULTURE: Record<string, string[]> = {
  blood: ['escherichia coli', 'klebsiella pneumoniae', 'staphylococcus aureus', 'enterococcus faecalis', 'other'],
  urine: ['escherichia coli', 'klebsiella pneumoniae', 'proteus mirabilis', 'pseudomonas aeruginosa', 'other'],
  respiratory: ['pseudomonas aeruginosa', 'staphylococcus aureus', 'klebsiella pneumoniae', 'other'],
}

const WARD_OPTIONS: { value: WardType; label: string; description: string }[] = [
  { value: 'general', label: 'General Ward (IP)', description: 'Standard inpatient ward' },
  { value: 'icu',     label: 'ICU',               description: 'Intensive care unit' },
  { value: 'er',      label: 'Emergency Room',    description: 'Emergency / acute presentation' },
]

type FormState = {
  culture_description: string
  organism: string
  age: string
  gender: 'male' | 'female'
  wbc: string
  cr: string
  lactate: string
  procalcitonin: string
  ward: WardType
}

type FormErrors = {
  culture_description?: string
  organism?: string
  age?: string
}

function displayName(value: string) {
  return value
    .split(' ')
    .map((part) => part.charAt(0).toUpperCase() + part.slice(1))
    .join(' ')
}

function LabField({
  id,
  label,
  unit,
  hint,
  value,
  onChange,
}: {
  id: string
  label: string
  unit: string
  hint: string
  value: string
  onChange: (e: React.ChangeEvent<HTMLInputElement>) => void
}) {
  return (
    <div>
      <label htmlFor={id} className="block text-sm font-medium text-gray-700 mb-1">
        {label}
        <span className="ml-1 text-xs font-normal text-gray-400">({unit})</span>
        <span className="ml-1 text-xs font-normal text-blue-400">optional</span>
      </label>
      <input
        type="number"
        id={id}
        name={id}
        step="any"
        min="0"
        value={value}
        onChange={onChange}
        placeholder="—"
        className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors placeholder:text-gray-300"
      />
      <p className="mt-1 text-xs text-gray-400">{hint}</p>
    </div>
  )
}

export default function PatientForm({
  onSubmit,
  loading,
  hasSubmitted = false,
  onReset,
  locale,
  localeOrganisms = [],
}: ARMDFormProps) {
  const isAntibiogram = locale !== 'us_armd'
  const [organismsByCulture, setOrganismsByCulture] = useState<Record<string, string[]>>(
    FALLBACK_ORGANISMS_BY_CULTURE
  )
  const [form, setForm] = useState<FormState>({
    culture_description: '',
    organism: '',
    age: '',
    gender: 'male',
    wbc: '',
    cr: '',
    lactate: '',
    procalcitonin: '',
    ward: 'general',
  })
  const [errors, setErrors] = useState<FormErrors>({})

  // Switching locale changes the organism vocabulary — clear the stale selection.
  useEffect(() => {
    setForm((prev) => ({ ...prev, organism: '' }))
    setErrors((prev) => ({ ...prev, organism: '' }))
  }, [locale])

  useEffect(() => {
    let mounted = true

    async function loadCatalog() {
      try {
        const catalog = await getARMDOrganismCatalog()
        if (mounted && catalog.organisms_by_culture) {
          setOrganismsByCulture(catalog.organisms_by_culture)
        }
      } catch {
        if (mounted) {
          setOrganismsByCulture(FALLBACK_ORGANISMS_BY_CULTURE)
        }
      }
    }

    loadCatalog()

    return () => {
      mounted = false
    }
  }, [])

  const cultureSites = useMemo(
    () => Object.keys(organismsByCulture).sort(),
    [organismsByCulture]
  )

  // US locale: organisms are culture-specific (from the catalog).
  // Antibiogram locale (e.g. Pakistan): organisms come from the local antibiogram
  // and are NOT culture-filtered; those without data are shown but disabled.
  const organismChoices = useMemo<OrganismChoice[]>(() => {
    if (isAntibiogram) {
      return localeOrganisms.map((o) => ({
        value: o.name,
        label: o.has_data ? o.display_name : `${o.display_name} — data pending`,
        disabled: !o.has_data,
      }))
    }
    return (organismsByCulture[form.culture_description] ?? []).map((o) => ({
      value: o,
      label: displayName(o),
      disabled: false,
    }))
  }, [isAntibiogram, localeOrganisms, organismsByCulture, form.culture_description])

  const organismSelectable = isAntibiogram || Boolean(form.culture_description)

  const handleChange = (e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>) => {
    const { name, value } = e.target
    setForm((prev) => ({
      ...prev,
      [name]: value,
      // US path scopes organisms by culture; reset the pick when culture changes.
      ...(name === 'culture_description' && !isAntibiogram ? { organism: '' } : {}),
    }))
    if (name in errors) {
      setErrors((prev) => ({ ...prev, [name]: '' }))
    }
  }

  const validateAge = (v: string) => {
    if (!v.trim()) return 'Age is required'
    const n = Number(v)
    if (!Number.isInteger(n) || n < 0 || n > 150) return 'Enter a whole number between 0 and 150'
    return ''
  }

  const validate = (): boolean => {
    const next: FormErrors = {}
    if (!form.culture_description) next.culture_description = 'Select a culture site'
    const enabled = organismChoices.filter((c) => !c.disabled).map((c) => c.value)
    if (!form.organism.trim()) {
      next.organism = 'Select an organism'
    } else if (!enabled.includes(form.organism)) {
      next.organism = isAntibiogram
        ? 'Select an organism with local antibiogram data'
        : 'Select an organism from the list or choose Other'
    }
    const ageErr = validateAge(form.age)
    if (ageErr) next.age = ageErr
    setErrors(next)
    return Object.keys(next).length === 0
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!validate()) return
    const data: ARMDFormData = {
      culture_description: form.culture_description,
      organism: form.organism.trim().toLowerCase(),
      age: Number(form.age),
      gender: form.gender,
      wbc: form.wbc.trim() ? Number(form.wbc) : null,
      cr: form.cr.trim() ? Number(form.cr) : null,
      lactate: form.lactate.trim() ? Number(form.lactate) : null,
      procalcitonin: form.procalcitonin.trim() ? Number(form.procalcitonin) : null,
      ward: form.ward,
      locale,
    }
    onSubmit(data)
  }

  const handleReset = () => {
    setForm({
      culture_description: '',
      organism: '',
      age: '',
      gender: 'male',
      wbc: '',
      cr: '',
      lactate: '',
      procalcitonin: '',
      ward: 'general',
    })
    setErrors({})
    onReset?.()
  }

  const canSubmit =
    !loading &&
    Boolean(form.culture_description) &&
    Boolean(form.organism) &&
    !validateAge(form.age)

  return (
    <div className="bg-white rounded-2xl shadow-xl overflow-hidden">
      {/* Header */}
      <div className="bg-gradient-to-r from-blue-600 to-indigo-600 px-6 py-4">
        <div className="flex items-center gap-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-full bg-white/15 text-lg">🧬</span>
          <div>
            <h2 className="text-xl font-semibold text-white">Clinical Input</h2>
            <p className="text-blue-100 text-sm">ARMD model · culture, demographics &amp; labs</p>
          </div>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="p-6 space-y-6">

        {/* ── Section 1: Culture & Organism ── */}
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-widest text-gray-400 mb-3">Microbiology</h3>
          <div className="grid md:grid-cols-2 gap-4">
            {/* Culture site */}
            <div>
              <label htmlFor="culture_description" className="block text-sm font-medium text-gray-700 mb-1">
                Culture Site <span className="text-red-500">*</span>
              </label>
              <select
                id="culture_description"
                name="culture_description"
                value={form.culture_description}
                onChange={handleChange}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
              >
                <option value="">Select culture site…</option>
                {cultureSites.map((s) => (
                  <option key={s} value={s}>
                    {displayName(s)}
                  </option>
                ))}
              </select>
              {errors.culture_description && (
                <p className="mt-1 text-xs text-red-600">{errors.culture_description}</p>
              )}
            </div>

            {/* Organism */}
            <div>
              <label htmlFor="organism" className="block text-sm font-medium text-gray-700 mb-1">
                Organism <span className="text-red-500">*</span>
              </label>
              <select
                id="organism"
                name="organism"
                value={form.organism}
                onChange={handleChange}
                disabled={!organismSelectable}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 disabled:bg-gray-50 disabled:text-gray-400 transition-colors"
              >
                <option value="">
                  {organismSelectable
                    ? 'Select organism…'
                    : 'Select culture site first'}
                </option>
                {organismChoices.map((o) => (
                  <option key={o.value} value={o.value} disabled={o.disabled}>
                    {o.label}
                  </option>
                ))}
              </select>
              {errors.organism && (
                <p className="mt-1 text-xs text-red-600">{errors.organism}</p>
              )}
            </div>
          </div>
        </div>

        {/* ── Section 2: Demographics ── */}
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-widest text-gray-400 mb-3">Demographics</h3>
          <div className="grid md:grid-cols-3 gap-4">
            {/* Age */}
            <div>
              <label htmlFor="age" className="block text-sm font-medium text-gray-700 mb-1">
                Age (years) <span className="text-red-500">*</span>
              </label>
              <input
                type="number"
                id="age"
                name="age"
                min="0"
                max="150"
                value={form.age}
                onChange={handleChange}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
              />
              {errors.age && <p className="mt-1 text-xs text-red-600">{errors.age}</p>}
            </div>

            {/* Gender */}
            <div>
              <span className="block text-sm font-medium text-gray-700 mb-1">Gender</span>
              <div className="flex gap-4 mt-2">
                {(['male', 'female'] as const).map((g) => (
                  <label key={g} className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="radio"
                      name="gender"
                      value={g}
                      checked={form.gender === g}
                      onChange={handleChange}
                      className="text-blue-600 focus:ring-blue-500"
                    />
                    <span className="text-sm text-gray-700 capitalize">{g}</span>
                  </label>
                ))}
              </div>
            </div>

            {/* Ward */}
            <div>
              <label htmlFor="ward" className="block text-sm font-medium text-gray-700 mb-1">
                Ward Location
              </label>
              <select
                id="ward"
                name="ward"
                value={form.ward}
                onChange={handleChange}
                className="w-full px-3 py-2 border border-gray-300 rounded-lg text-sm focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
              >
                {WARD_OPTIONS.map((o) => (
                  <option key={o.value} value={o.value}>
                    {o.label}
                  </option>
                ))}
              </select>
              <p className="mt-1 text-xs text-gray-400">
                {WARD_OPTIONS.find((o) => o.value === form.ward)?.description}
              </p>
            </div>
          </div>
        </div>

        {/* ── Section 3: Lab Values ── */}
        <div>
          <h3 className="text-xs font-semibold uppercase tracking-widest text-gray-400 mb-3">
            Laboratory Values
            <span className="ml-2 text-blue-400 normal-case tracking-normal font-normal">all optional</span>
          </h3>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-4">
            <LabField
              id="wbc"
              label="WBC"
              unit="×10³/μL"
              hint="Normal: 4–11"
              value={form.wbc}
              onChange={handleChange}
            />
            <LabField
              id="cr"
              label="Creatinine"
              unit="mg/dL"
              hint="Normal: 0.6–1.2"
              value={form.cr}
              onChange={handleChange}
            />
            <LabField
              id="lactate"
              label="Lactate"
              unit="mmol/L"
              hint="Normal: 0.5–2.0"
              value={form.lactate}
              onChange={handleChange}
            />
            <LabField
              id="procalcitonin"
              label="Procalcitonin"
              unit="ng/mL"
              hint="Normal: <0.1"
              value={form.procalcitonin}
              onChange={handleChange}
            />
          </div>
        </div>

        {/* ── Actions ── */}
        <div className="pt-2">
          <button
            type="submit"
            disabled={!canSubmit}
            className={`w-full bg-gradient-to-r from-blue-600 to-indigo-600 text-white font-semibold py-3 px-6 rounded-lg hover:from-blue-700 hover:to-indigo-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center justify-center ${loading ? 'animate-pulse' : ''}`}
          >
            {loading ? (
              <>
                <svg className="animate-spin -ml-1 mr-3 h-5 w-5 text-white" fill="none" viewBox="0 0 24 24">
                  <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
                  <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
                </svg>
                Analyzing…
              </>
            ) : (
              'Get Recommendations'
            )}
          </button>

          {hasSubmitted && onReset && (
            <button
              type="button"
              onClick={handleReset}
              className="mt-3 w-full rounded-lg border border-slate-200 bg-white px-6 py-3 text-sm font-semibold text-slate-700 transition hover:border-slate-300 hover:bg-slate-50"
            >
              New Search
            </button>
          )}
        </div>
      </form>
    </div>
  )
}
