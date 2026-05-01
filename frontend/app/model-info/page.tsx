'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'
import { getARMDModelInfo, ARMDModelInfoResponse, ARMDTestSummaryRow } from '@/services/api'

function Spinner() {
  return (
    <div className="flex items-center justify-center py-16">
      <div className="h-10 w-10 animate-spin rounded-full border-4 border-slate-200 border-t-teal-600" />
    </div>
  )
}

function formatPercent(value: number) {
  return `${(value * 100).toFixed(1)}%`
}

function formatLabel(value: string) {
  return value.replace(/_/g, ' ')
}

function metricRows(row?: ARMDTestSummaryRow) {
  if (!row) return []
  return [
    ['ROC AUC', row.roc_auc],
    ['F1', row.f1_1],
    ['Recall', row.recall_1],
    ['Precision', row.precision_1],
    ['Accuracy', row.accuracy],
    ['Balanced accuracy', row.balanced_accuracy],
  ]
}

export default function ModelInfoPage() {
  const [data, setData] = useState<ARMDModelInfoResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let mounted = true

    async function loadModelInfo() {
      try {
        setLoading(true)
        setError(null)
        const response = await getARMDModelInfo()
        if (mounted) setData(response)
      } catch {
        if (mounted) {
          setError('Unable to reach the model info API at http://localhost:8000/api/v2/model-info.')
        }
      } finally {
        if (mounted) setLoading(false)
      }
    }

    loadModelInfo()

    return () => {
      mounted = false
    }
  }, [])

  const selectedTestRun = useMemo(() => {
    if (!data?.test_summary?.length) return undefined
    return data.test_summary.find((row) => row.threshold === data.best_threshold) ?? data.test_summary[0]
  }, [data])

  const featureGroupCounts = useMemo(() => {
    const groups = data?.feature_groups
    if (!groups) return []

    return [
      ['Categorical', groups.categorical.length],
      ['Numeric', groups.numeric.length],
      ['Binary history and ward', groups.binary.length],
    ]
  }, [data])

  return (
    <main className="min-h-screen bg-slate-50 text-slate-900">
      <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
        <div className="mb-6 flex items-center justify-between gap-4">
          <Link
            href="/"
            className="inline-flex items-center rounded-lg border border-slate-300 bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-sm transition hover:border-slate-400 hover:bg-slate-50"
          >
            Back to home
          </Link>
          {data && (
            <span className={`rounded-lg border px-3 py-2 text-sm font-medium ${data.available ? 'border-emerald-200 bg-emerald-50 text-emerald-700' : 'border-rose-200 bg-rose-50 text-rose-700'}`}>
              {data.available ? 'V2 model loaded' : 'V2 model unavailable'}
            </span>
          )}
        </div>

        <header className="mb-8 border-b border-slate-200 pb-6">
          <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
            Model Performance Dashboard
          </h1>
          <p className="mt-3 max-w-3xl text-base text-slate-600">
            ARMD RandomForest recommendation model with hybrid dosage and route prediction.
          </p>
        </header>

        {loading ? (
          <section className="rounded-lg border border-slate-200 bg-white shadow-sm">
            <Spinner />
          </section>
        ) : error ? (
          <section className="rounded-lg border border-rose-200 bg-rose-50 px-6 py-8 text-rose-800 shadow-sm">
            <p className="font-semibold">Model info unavailable</p>
            <p className="mt-2 text-sm">{error}</p>
          </section>
        ) : data ? (
          <>
            <section className="mb-6 grid gap-4 md:grid-cols-4">
              <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
                <p className="text-sm font-medium text-slate-500">Recommendation model</p>
                <p className="mt-2 text-xl font-semibold text-slate-900">{data.model_type}</p>
              </div>
              <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
                <p className="text-sm font-medium text-slate-500">Antibiotics scored</p>
                <p className="mt-2 text-3xl font-semibold text-slate-900">{data.n_antibiotics}</p>
              </div>
              <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
                <p className="text-sm font-medium text-slate-500">Model features</p>
                <p className="mt-2 text-3xl font-semibold text-slate-900">{data.n_features}</p>
              </div>
              <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
                <p className="text-sm font-medium text-slate-500">Tuned threshold</p>
                <p className="mt-2 text-3xl font-semibold text-slate-900">{data.best_threshold.toFixed(2)}</p>
              </div>
            </section>

            <section className="mb-6 grid gap-4 lg:grid-cols-3">
              {metricRows(selectedTestRun).map(([label, value]) => (
                <div key={label} className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
                  <p className="text-sm font-medium text-slate-500">{label}</p>
                  <p className="mt-2 text-2xl font-semibold text-slate-900">{formatPercent(Number(value))}</p>
                </div>
              ))}
            </section>

            <section className="mb-6 grid gap-6 lg:grid-cols-2">
              <div className="rounded-lg border border-slate-200 bg-white shadow-sm">
                <div className="border-b border-slate-200 px-5 py-4">
                  <h2 className="text-lg font-semibold text-slate-900">Held-out Test Results</h2>
                </div>
                <div className="overflow-x-auto">
                  <table className="min-w-full divide-y divide-slate-200">
                    <thead className="bg-slate-50">
                      <tr>
                        {['Threshold', 'Accuracy', 'Precision', 'Recall', 'F1', 'ROC AUC'].map((heading) => (
                          <th key={heading} className="px-5 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">
                            {heading}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-slate-200">
                      {data.test_summary.map((row) => (
                        <tr key={`${row.split}-${row.threshold}`} className={row.threshold === data.best_threshold ? 'bg-teal-50/70' : 'hover:bg-slate-50'}>
                          <td className="px-5 py-4 text-sm font-semibold text-slate-900">{row.threshold.toFixed(2)}</td>
                          <td className="px-5 py-4 text-sm text-slate-700">{formatPercent(row.accuracy)}</td>
                          <td className="px-5 py-4 text-sm text-slate-700">{formatPercent(row.precision_1)}</td>
                          <td className="px-5 py-4 text-sm text-slate-700">{formatPercent(row.recall_1)}</td>
                          <td className="px-5 py-4 text-sm text-slate-700">{formatPercent(row.f1_1)}</td>
                          <td className="px-5 py-4 text-sm text-slate-700">{formatPercent(row.roc_auc)}</td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </div>

              <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
                <h2 className="text-lg font-semibold text-slate-900">Dosage And Route Model</h2>
                <div className="mt-5 grid gap-4 sm:grid-cols-2">
                  <div>
                    <p className="text-sm font-medium text-slate-500">Model type</p>
                    <p className="mt-1 font-semibold text-slate-900">{data.dosage_model.model_type}</p>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-slate-500">Status</p>
                    <p className="mt-1 font-semibold text-slate-900">{data.dosage_model.available ? 'ML fallback loaded' : 'Static fallback only'}</p>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-slate-500">Lookup entries</p>
                    <p className="mt-1 text-2xl font-semibold text-slate-900">{data.dosage_model.lookup_entries.toLocaleString()}</p>
                  </div>
                  <div>
                    <p className="text-sm font-medium text-slate-500">Static fallback antibiotics</p>
                    <p className="mt-1 text-2xl font-semibold text-slate-900">{data.dosage_model.fallback_antibiotics}</p>
                  </div>
                </div>
              </div>
            </section>

            <section className="mb-6 grid gap-6 lg:grid-cols-2">
              <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
                <h2 className="text-lg font-semibold text-slate-900">Top Feature Importances</h2>
                <div className="mt-5 space-y-3">
                  {data.top_feature_importances.map((item) => (
                    <div key={item.feature}>
                      <div className="mb-1 flex items-center justify-between gap-3 text-sm">
                        <span className="font-medium text-slate-700">{formatLabel(item.feature)}</span>
                        <span className="text-slate-500">{formatPercent(item.importance)}</span>
                      </div>
                      <div className="h-2 rounded-full bg-slate-100">
                        <div className="h-2 rounded-full bg-teal-600" style={{ width: `${Math.min(item.importance * 100, 100)}%` }} />
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
                <h2 className="text-lg font-semibold text-slate-900">Feature Groups</h2>
                <div className="mt-5 grid gap-4 sm:grid-cols-3">
                  {featureGroupCounts.map(([label, count]) => (
                    <div key={label} className="border-l-4 border-teal-500 pl-4">
                      <p className="text-sm font-medium text-slate-500">{label}</p>
                      <p className="mt-1 text-2xl font-semibold text-slate-900">{count}</p>
                    </div>
                  ))}
                </div>
                <div className="mt-6 flex flex-wrap gap-2">
                  {[...data.feature_groups.categorical, ...data.feature_groups.numeric].map((feature) => (
                    <span key={feature} className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-1 text-sm text-slate-700">
                      {formatLabel(feature)}
                    </span>
                  ))}
                </div>
              </div>
            </section>

            <section className="rounded-lg border border-slate-200 bg-white p-5 shadow-sm">
              <h2 className="text-lg font-semibold text-slate-900">Antibiotic Inventory</h2>
              <div className="mt-5 grid gap-2 sm:grid-cols-2 md:grid-cols-3 lg:grid-cols-4">
                {data.antibiotics.map((antibiotic) => (
                  <span key={antibiotic} className="rounded-lg border border-slate-200 bg-slate-50 px-3 py-2 text-sm font-medium text-slate-700">
                    {formatLabel(antibiotic)}
                  </span>
                ))}
              </div>
            </section>
          </>
        ) : null}
      </div>
    </main>
  )
}
