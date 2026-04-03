'use client'

import { useState } from 'react'
import { PatientFormProps, PatientFormData } from '@/types'

const organisms = [
  { value: 'E. coli', label: 'E. coli' },
  { value: 'K. pneumoniae', label: 'K. pneumoniae' },
  { value: 'P. aeruginosa', label: 'P. aeruginosa' },
  { value: 'A. baumannii', label: 'A. baumannii' },
  { value: 'S. aureus', label: 'S. aureus' },
  { value: 'E. faecium', label: 'E. faecium' },
  { value: 'S. pneumoniae', label: 'S. pneumoniae' },
  { value: 'Enterococcus spp', label: 'Enterococcus spp' },
  {
    value: 'COAG NEGATIVE STAPHYLOCOCCUS',
    label: 'COAG NEGATIVE STAPHYLOCOCCUS',
  },
  { value: 'KLEBSIELLA OXYTOCA', label: 'KLEBSIELLA OXYTOCA' },
  { value: 'PROTEUS MIRABILIS', label: 'PROTEUS MIRABILIS' },
  {
    value: 'STAPHYLOCOCCUS EPIDERMIDIS',
    label: 'STAPHYLOCOCCUS EPIDERMIDIS',
  },
  { value: 'ENTEROCOCCUS FAECALIS', label: 'ENTEROCOCCUS FAECALIS' },
  { value: 'Other', label: 'Other' },
]

const kidneyFunctionOptions = [
  { value: 'normal', label: 'Normal' },
  { value: 'mild', label: 'Mild Impairment' },
  { value: 'low', label: 'Impaired / Low' },
  { value: 'severe', label: 'Severe / Dialysis' },
]

const severityOptions = [
  { value: 'low', label: 'Low' },
  { value: 'medium', label: 'Moderate (medium)' },
  { value: 'high', label: 'High' },
  { value: 'critical', label: 'Critical' },
]

type FormState = {
  organism: string
  age: string
  gender: 'M' | 'F'
  kidney_function: PatientFormData['kidney_function']
  severity: PatientFormData['severity']
}

type FormErrors = {
  organism?: string
  age?: string
}

export default function PatientForm({
  onSubmit,
  loading,
  hasSubmitted = false,
  onReset,
}: PatientFormProps) {
  const [formData, setFormData] = useState<FormState>({
    organism: '',
    age: '',
    gender: 'M',
    kidney_function: 'normal',
    severity: 'medium',
  })
  const [errors, setErrors] = useState<FormErrors>({})

  const handleChange = (
    e: React.ChangeEvent<HTMLInputElement | HTMLSelectElement>
  ) => {
    const { name, value } = e.target
    setFormData((prev) => ({
      ...prev,
      [name]: value,
    }))

    if (name === 'organism') {
      setErrors((prev) => ({
        ...prev,
        organism: value ? '' : 'Please select an organism',
      }))
    }

    if (name === 'age') {
      setErrors((prev) => ({
        ...prev,
        age: validateAge(value),
      }))
    }
  }

  const validateAge = (ageValue: string) => {
    if (!ageValue.trim()) {
      return 'Age is required'
    }

    const ageNumber = Number(ageValue)
    if (!Number.isInteger(ageNumber)) {
      return 'Age must be a whole number'
    }
    if (ageNumber < 1 || ageNumber > 120) {
      return 'Age must be between 1 and 120'
    }

    return ''
  }

  const validateForm = () => {
    const nextErrors: FormErrors = {}

    if (!formData.organism) {
      nextErrors.organism = 'Please select an organism'
    }

    const ageError = validateAge(formData.age)
    if (ageError) {
      nextErrors.age = ageError
    }

    setErrors(nextErrors)
    return Object.keys(nextErrors).length === 0
  }

  const handleSubmit = (e: React.FormEvent) => {
    e.preventDefault()
    if (!validateForm()) {
      return
    }

    onSubmit({
      organism: formData.organism,
      age: Number(formData.age),
      gender: formData.gender,
      kidney_function: formData.kidney_function,
      severity: formData.severity,
    })
  }

  const handleReset = () => {
    setFormData({
      organism: '',
      age: '',
      gender: 'M',
      kidney_function: 'normal',
      severity: 'medium',
    })
    setErrors({})
    onReset?.()
  }

  const canSubmit =
    !loading &&
    Boolean(formData.organism) &&
    Boolean(formData.age.trim()) &&
    !validateAge(formData.age) &&
    !errors.organism &&
    !errors.age

  return (
    <div className="bg-white rounded-2xl shadow-xl overflow-hidden">
      <div className="bg-gradient-to-r from-blue-600 to-indigo-600 px-6 py-4">
        <div className="flex items-center gap-3">
          <span className="flex h-9 w-9 items-center justify-center rounded-full bg-white/15 text-lg">
            🦠
          </span>
          <div>
            <h2 className="text-xl font-semibold text-white">Patient Information</h2>
            <p className="text-blue-100 text-sm">
              Clinical inputs used to estimate antibiotic susceptibility
            </p>
          </div>
        </div>
      </div>

      <form onSubmit={handleSubmit} className="p-6">
        <div className="grid md:grid-cols-2 gap-6">
          {/* Organism Selection */}
          <div className="md:col-span-2">
            <label
              htmlFor="organism"
              className="block text-sm font-medium text-gray-700 mb-2"
            >
              Organism <span className="text-red-500">*</span>
            </label>
            <select
              id="organism"
              name="organism"
              value={formData.organism}
              onChange={handleChange}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
              required
            >
              <option value="">Select organism...</option>
              {organisms.map((org) => (
                <option key={org.value} value={org.value}>
                  {org.label}
                </option>
              ))}
            </select>
            {errors.organism && (
              <p className="mt-2 text-xs text-red-600">{errors.organism}</p>
            )}
            <p className="mt-2 text-xs text-gray-500">
              Select the likely pathogen to match the resistance patterns used by the model.
            </p>
          </div>

          {/* Age */}
          <div>
            <label
              htmlFor="age"
              className="block text-sm font-medium text-gray-700 mb-2"
            >
              Age (years)
            </label>
            <input
              type="number"
              id="age"
              name="age"
              min="1"
              max="120"
              value={formData.age}
              onChange={handleChange}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
            />
            {errors.age && <p className="mt-2 text-xs text-red-600">{errors.age}</p>}
            <p className="mt-2 text-xs text-gray-500">
              Patient age influences dosing safety, severity risk, and model context.
            </p>
          </div>

          {/* Gender */}
          <div>
            <label className="block text-sm font-medium text-gray-700 mb-2">
              Gender
            </label>
            <div className="flex gap-4">
              <label className="flex items-center cursor-pointer">
                <input
                  type="radio"
                  name="gender"
                  value="M"
                  checked={formData.gender === 'M'}
                  onChange={handleChange}
                  className="mr-2 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-gray-700">Male</span>
              </label>
              <label className="flex items-center cursor-pointer">
                <input
                  type="radio"
                  name="gender"
                  value="F"
                  checked={formData.gender === 'F'}
                  onChange={handleChange}
                  className="mr-2 text-blue-600 focus:ring-blue-500"
                />
                <span className="text-gray-700">Female</span>
              </label>
            </div>
            <p className="mt-2 text-xs text-gray-500">
              Gender is used as a demographic feature during susceptibility prediction.
            </p>
          </div>

          {/* Kidney Function */}
          <div>
            <label
              htmlFor="kidney_function"
              className="block text-sm font-medium text-gray-700 mb-2"
            >
              Kidney Function
            </label>
            <select
              id="kidney_function"
              name="kidney_function"
              value={formData.kidney_function}
              onChange={handleChange}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
            >
              {kidneyFunctionOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <p className="mt-2 text-xs text-gray-500">
              (CrCl: Normal &gt;90, Mild 60–90, Low 30–60, Severe &lt;30 mL/min)
            </p>
          </div>

          {/* Severity */}
          <div>
            <label
              htmlFor="severity"
              className="block text-sm font-medium text-gray-700 mb-2"
            >
              Infection Severity
            </label>
            <select
              id="severity"
              name="severity"
              value={formData.severity}
              onChange={handleChange}
              className="w-full px-4 py-2 border border-gray-300 rounded-lg focus:ring-2 focus:ring-blue-500 focus:border-blue-500 transition-colors"
            >
              {severityOptions.map((option) => (
                <option key={option.value} value={option.value}>
                  {option.label}
                </option>
              ))}
            </select>
            <p className="mt-2 text-xs text-gray-500">
              (Low: Outpatient, Moderate: Ward, High: ICU, Critical: Septic shock)
            </p>
          </div>
        </div>

        {/* Submit Button */}
        <div className="mt-8">
          <button
            type="submit"
            disabled={!canSubmit}
            className={`w-full bg-gradient-to-r from-blue-600 to-indigo-600 text-white font-semibold py-3 px-6 rounded-lg hover:from-blue-700 hover:to-indigo-700 focus:outline-none focus:ring-2 focus:ring-blue-500 focus:ring-offset-2 disabled:opacity-50 disabled:cursor-not-allowed transition-all flex items-center justify-center ${loading ? 'animate-pulse' : ''}`}
          >
            {loading ? (
              <>
                <svg
                  className="animate-spin -ml-1 mr-3 h-5 w-5 text-white"
                  xmlns="http://www.w3.org/2000/svg"
                  fill="none"
                  viewBox="0 0 24 24"
                >
                  <circle
                    className="opacity-25"
                    cx="12"
                    cy="12"
                    r="10"
                    stroke="currentColor"
                    strokeWidth="4"
                  ></circle>
                  <path
                    className="opacity-75"
                    fill="currentColor"
                    d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"
                  ></path>
                </svg>
                Analyzing...
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
