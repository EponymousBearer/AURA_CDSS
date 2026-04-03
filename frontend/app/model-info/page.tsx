'use client'

import Link from 'next/link'
import { useEffect, useMemo, useState } from 'react'
import { getModelInfo, ModelInfoResponse } from '@/services/api'

function Spinner() {
  return (
    <div className="flex items-center justify-center py-16">
      <div className="h-12 w-12 animate-spin rounded-full border-4 border-slate-200 border-t-blue-600" />
    </div>
  )
}

function aucClass(auc: number) {
  if (auc >= 0.8) return 'text-emerald-700 bg-emerald-50 border-emerald-200'
  if (auc >= 0.65) return 'text-amber-700 bg-amber-50 border-amber-200'
  return 'text-rose-700 bg-rose-50 border-rose-200'
}

function statusClass(status: string) {
  if (status === 'included') return 'bg-emerald-100 text-emerald-800 border-emerald-200'
  return 'bg-slate-100 text-slate-600 border-slate-200'
}

export default function ModelInfoPage() {
  const [data, setData] = useState<ModelInfoResponse | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let mounted = true

    async function loadModelInfo() {
      try {
        setLoading(true)
        setError(null)
        const response = await getModelInfo()
        if (mounted) {
          setData(response)
        }
      } catch {
        if (mounted) {
          setError('Unable to reach the model info API at http://localhost:8000/api/v1/model-info.')
        }
      } finally {
        if (mounted) {
          setLoading(false)
        }
      }
    }

    loadModelInfo()

    return () => {
      mounted = false
    }
  }, [])

  const summary = useMemo(() => {
    const antibiotics = data?.antibiotics ?? []
    const active = antibiotics.filter((item) => item.status === 'included')
    const avgAuc = active.length
      ? active.reduce((sum, item) => sum + item.auc, 0) / active.length
      : 0

    return {
      total: data?.n_antibiotics ?? 0,
      averageAuc: avgAuc,
      trainingSamples: data?.training_samples ?? 0,
      trainedAt: data?.model_trained_at,
    }
  }, [data])

  return (
    <main className="min-h-screen bg-[radial-gradient(circle_at_top,_#eff6ff_0%,_#f8fafc_40%,_#eef2ff_100%)] text-slate-900">
      <div className="mx-auto max-w-7xl px-4 py-10 sm:px-6 lg:px-8">
        <div className="mb-8 flex items-center justify-between gap-4">
          <Link
            href="/"
            className="inline-flex items-center rounded-full border border-slate-200 bg-white px-4 py-2 text-sm font-medium text-slate-700 shadow-sm transition hover:border-slate-300 hover:bg-slate-50"
          >
            Back to home
          </Link>
          {summary.trainedAt && (
            <span className="text-sm text-slate-500">
              Trained at <span className="font-medium text-slate-700">{summary.trainedAt}</span>
            </span>
          )}
        </div>

        <div className="mb-10 rounded-3xl border border-white/60 bg-white/80 px-6 py-8 shadow-xl shadow-slate-200/60 backdrop-blur sm:px-8">
          <h1 className="text-3xl font-semibold tracking-tight sm:text-4xl">
            Model Performance Dashboard
          </h1>
          <p className="mt-3 text-base text-slate-600 sm:text-lg">
            CatBoost models trained on Dryad Microbiology Dataset
          </p>
        </div>

        {loading ? (
          <div className="rounded-3xl border border-white/60 bg-white/80 shadow-xl shadow-slate-200/60 backdrop-blur">
            <Spinner />
          </div>
        ) : error ? (
          <div className="rounded-3xl border border-rose-200 bg-rose-50 px-6 py-8 text-rose-800 shadow-sm">
            <p className="font-semibold">Model info unavailable</p>
            <p className="mt-2 text-sm">{error}</p>
            <div className="mt-6">
              <Link
                href="/"
                className="inline-flex items-center rounded-full bg-rose-600 px-4 py-2 text-sm font-medium text-white transition hover:bg-rose-700"
              >
                Return to main page
              </Link>
            </div>
          </div>
        ) : (
          <>
            <section className="mb-8 grid gap-4 md:grid-cols-3">
              <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
                <p className="text-sm font-medium text-slate-500">Total antibiotics modeled</p>
                <p className="mt-3 text-3xl font-semibold text-slate-900">{summary.total}</p>
              </div>
              <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
                <p className="text-sm font-medium text-slate-500">Average AUC across included models</p>
                <p className="mt-3 text-3xl font-semibold text-slate-900">
                  {(summary.averageAuc * 100).toFixed(1)}%
                </p>
              </div>
              <div className="rounded-3xl border border-slate-200 bg-white p-6 shadow-sm">
                <p className="text-sm font-medium text-slate-500">Training dataset size</p>
                <p className="mt-3 text-3xl font-semibold text-slate-900">{summary.trainingSamples.toLocaleString()}</p>
              </div>
            </section>

            <section className="overflow-hidden rounded-3xl border border-slate-200 bg-white shadow-xl shadow-slate-200/60">
              <div className="border-b border-slate-200 px-6 py-4">
                <h2 className="text-lg font-semibold text-slate-900">Antibiotic model quality</h2>
                <p className="text-sm text-slate-500">AUC, F1, accuracy, and deployment status for each antibiotic model.</p>
              </div>

              <div className="overflow-x-auto">
                <table className="min-w-full divide-y divide-slate-200">
                  <thead className="bg-slate-50">
                    <tr>
                      <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">Antibiotic name</th>
                      <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">AUC score</th>
                      <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">F1 score</th>
                      <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">Accuracy</th>
                      <th className="px-6 py-3 text-left text-xs font-semibold uppercase tracking-wide text-slate-500">Status</th>
                    </tr>
                  </thead>
                  <tbody className="divide-y divide-slate-200">
                    {data.antibiotics.map((item) => (
                      <tr key={item.name} className="hover:bg-slate-50/70">
                        <td className="px-6 py-4 text-sm font-medium text-slate-900">{item.name}</td>
                        <td className="px-6 py-4 text-sm">
                          <span className={`inline-flex rounded-full border px-3 py-1 font-semibold ${aucClass(item.auc)}`}>
                            {item.auc.toFixed(3)}
                          </span>
                        </td>
                        <td className="px-6 py-4 text-sm text-slate-700">{item.f1.toFixed(3)}</td>
                        <td className="px-6 py-4 text-sm text-slate-700">{item.accuracy.toFixed(3)}</td>
                        <td className="px-6 py-4 text-sm">
                          <span className={`inline-flex rounded-full border px-3 py-1 text-xs font-semibold uppercase tracking-wide ${statusClass(item.status)}`}>
                            {item.status === 'included' ? 'Active' : 'Excluded'}
                          </span>
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            </section>
          </>
        )}
      </div>
    </main>
  )
}