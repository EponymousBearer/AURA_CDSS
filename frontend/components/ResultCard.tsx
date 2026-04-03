'use client'

import { useState } from 'react'
import { getExplanation } from '@/services/api'
import { ResultCardProps } from '@/types'

const FEATURE_LABELS: Record<string, string> = {
  organism: 'Organism',
  age: 'Age',
  gender: 'Gender',
  kidney_function: 'Kidney function',
  severity: 'Severity',
}

export default function ResultCard({ recommendation, rank, patientData }: ResultCardProps) {
  const [isExplainOpen, setIsExplainOpen] = useState(false)
  const [isExplainLoading, setIsExplainLoading] = useState(false)
  const [explainError, setExplainError] = useState<string | null>(null)
  const [featureImportances, setFeatureImportances] = useState<Record<string, number> | null>(null)

  const getRankColor = (rank: number) => {
    switch (rank) {
      case 1:
        return 'from-green-500 to-emerald-600'
      case 2:
        return 'from-blue-500 to-cyan-600'
      case 3:
        return 'from-indigo-500 to-purple-600'
      default:
        return 'from-gray-500 to-gray-600'
    }
  }

  const getProbabilityColor = (prob: number) => {
    if (prob >= 0.8) return 'text-green-600'
    if (prob >= 0.6) return 'text-blue-600'
    if (prob >= 0.4) return 'text-yellow-600'
    return 'text-red-600'
  }

  const getProbabilityLabel = (prob: number) => {
    if (prob >= 0.85) return { label: 'Highly Susceptible', className: 'bg-emerald-100 text-emerald-800' }
    if (prob >= 0.7) return { label: 'Susceptible', className: 'bg-blue-100 text-blue-800' }
    if (prob >= 0.5) return { label: 'Moderately Susceptible', className: 'bg-amber-100 text-amber-800' }
    return { label: 'Resistant', className: 'bg-rose-100 text-rose-800' }
  }

  const featureOrder = ['organism', 'age', 'gender', 'kidney_function', 'severity']

  const explainabilityRows = featureOrder
    .map((feature) => ({
      key: feature,
      label: FEATURE_LABELS[feature] ?? feature,
      value: featureImportances?.[feature] ?? 0,
    }))
    .sort((left, right) => right.value - left.value)

  const handleExplain = async () => {
    if (!patientData) {
      setExplainError('Patient data is unavailable for this recommendation.')
      setIsExplainOpen(true)
      return
    }

    setIsExplainOpen(true)
    setIsExplainLoading(true)
    setExplainError(null)
    setFeatureImportances(null)

    try {
      const response = await getExplanation(patientData, recommendation.antibiotic)
      setFeatureImportances(response)
    } catch (error) {
      setExplainError('Unable to load explainability data for this recommendation.')
    } finally {
      setIsExplainLoading(false)
    }
  }

  return (
    <>
      <div className="bg-white rounded-xl shadow-lg overflow-hidden hover:shadow-xl transition-shadow">
      {/* Header with Rank */}
      <div className={`bg-gradient-to-r ${getRankColor(rank)} px-4 py-3`}>
        <div className="flex items-center justify-between">
          <h3 className="text-lg font-bold text-white">
            {recommendation.antibiotic}
          </h3>
          <span className="bg-white/20 text-white text-sm font-semibold px-3 py-1 rounded-full">
            #{rank}
          </span>
        </div>
      </div>

      {/* Content */}
      <div className="p-5 space-y-4">
        {/* Probability */}
        <div className="flex items-center justify-between">
          <span className="text-gray-600 font-medium">Susceptibility</span>
          <div className="text-right">
            <span className={`text-2xl font-bold ${getProbabilityColor(recommendation.probability)}`}>
              {(recommendation.probability * 100).toFixed(1)}%
            </span>
            <span className={`ml-2 text-sm font-medium ${getProbabilityColor(recommendation.probability)}`}>
              ({getProbabilityLabel(recommendation.probability).label})
            </span>
          </div>
        </div>

        <div className="flex justify-end">
          <span
            className={`inline-flex rounded-full px-3 py-1 text-xs font-semibold ${getProbabilityLabel(recommendation.probability).className}`}
          >
            {getProbabilityLabel(recommendation.probability).label}
          </span>
        </div>

        {/* Progress Bar */}
        <div className="w-full bg-gray-200 rounded-full h-2.5">
          <div
            className={`h-2.5 rounded-full bg-gradient-to-r ${getRankColor(rank)}`}
            style={{ width: `${recommendation.probability * 100}%` }}
          ></div>
        </div>

        {/* Dosing Information */}
        <div className="space-y-3 pt-2 border-t border-gray-100">
          <div className="flex justify-between">
            <span className="text-gray-500 text-sm">Dose</span>
            <span className="text-gray-800 font-medium text-sm text-right">
              {recommendation.dose}
            </span>
          </div>

          <div className="flex justify-between">
            <span className="text-gray-500 text-sm">Route</span>
            <span className={`font-medium text-sm ${
              recommendation.route === 'IV' ? 'text-red-600' : 'text-green-600'
            }`}>
              {recommendation.route}
            </span>
          </div>

          <div className="flex justify-between">
            <span className="text-gray-500 text-sm">Frequency</span>
            <span className="text-gray-800 font-medium text-sm text-right">
              {recommendation.frequency}
            </span>
          </div>

          <div className="flex justify-between">
            <span className="text-gray-500 text-sm">Duration</span>
            <span className="text-gray-800 font-medium text-sm text-right">
              {recommendation.duration}
            </span>
          </div>
        </div>

        {/* Clinical Notes */}
        <div className="group relative rounded-lg bg-gray-50 p-3">
          <div className="flex items-start gap-2 text-xs text-gray-600">
            <span className="font-semibold">Clinical Notes</span>
            <span className="relative inline-flex h-5 w-5 items-center justify-center rounded-full bg-gray-200 text-[10px] font-bold text-gray-700">
              ⓘ
              <span className="pointer-events-none absolute bottom-full right-0 mb-2 hidden w-64 rounded-lg bg-gray-900 px-3 py-2 text-left text-[11px] leading-5 text-white shadow-lg group-hover:block">
                Clinical notes provide a short bedside summary for the selected
                antibiotic, including why it appears in the top recommendations.
              </span>
            </span>
          </div>
          <p className="mt-2 text-xs leading-relaxed text-gray-600">
            {recommendation.clinical_notes}
          </p>
        </div>

        <button
          type="button"
          onClick={handleExplain}
          disabled={!patientData || isExplainLoading}
          className="w-full rounded-lg border border-indigo-200 bg-indigo-50 px-4 py-2 text-sm font-semibold text-indigo-700 transition hover:bg-indigo-100 disabled:cursor-not-allowed disabled:opacity-60"
        >
          {isExplainLoading ? 'Loading explanation...' : 'Explain'}
        </button>
      </div>
      </div>

      {isExplainOpen && (
        <div className="fixed inset-0 z-50 flex items-center justify-center bg-slate-950/60 px-4 py-6 backdrop-blur-sm">
          <div className="w-full max-w-xl rounded-2xl bg-white shadow-2xl">
            <div className="flex items-center justify-between border-b border-slate-200 px-6 py-4">
              <div>
                <p className="text-xs font-semibold uppercase tracking-[0.2em] text-indigo-600">Why this recommendation</p>
                <h4 className="text-xl font-bold text-slate-900">{recommendation.antibiotic}</h4>
              </div>
              <button
                type="button"
                onClick={() => setIsExplainOpen(false)}
                className="rounded-full bg-slate-100 px-3 py-1 text-sm font-semibold text-slate-700 transition hover:bg-slate-200"
              >
                Close
              </button>
            </div>

            <div className="px-6 py-5">
              {isExplainLoading && (
                <div className="rounded-xl bg-slate-50 p-4 text-sm text-slate-600">
                  Calculating SHAP feature importances...
                </div>
              )}

              {explainError && !isExplainLoading && (
                <div className="rounded-xl border border-rose-200 bg-rose-50 p-4 text-sm text-rose-700">
                  {explainError}
                </div>
              )}

              {featureImportances && !isExplainLoading && (
                <div className="space-y-4">
                  <div className="text-sm text-slate-600">
                    Feature contributions are normalized to 100% for this single prediction.
                  </div>
                  <div className="space-y-3">
                    {explainabilityRows.map((row) => (
                      <div key={row.key}>
                        <div className="mb-1 flex items-center justify-between text-sm font-medium text-slate-700">
                          <span>{row.label} ({row.value.toFixed(1)}%)</span>
                          <span>{row.value.toFixed(1)}%</span>
                        </div>
                        <div className="h-3 rounded-full bg-slate-100">
                          <div
                            className="h-3 rounded-full bg-gradient-to-r from-indigo-500 to-cyan-500"
                            style={{ width: `${row.value}%` }}
                          />
                        </div>
                      </div>
                    ))}
                  </div>
                </div>
              )}
            </div>
          </div>
        </div>
      )}
    </>
  )
}
