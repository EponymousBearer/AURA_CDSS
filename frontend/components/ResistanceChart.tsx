'use client'

import { ResistanceChartProps } from '@/types'

function getBarClass(probability: number) {
  const percentage = probability * 100
  if (percentage > 80) return 'bg-emerald-500'
  if (percentage >= 60) return 'bg-blue-500'
  if (percentage >= 40) return 'bg-amber-500'
  return 'bg-rose-500'
}

export default function ResistanceChart({ allPredictions, organism }: ResistanceChartProps) {
  const sortedPredictions = [...allPredictions].sort(
    (left, right) => right.probability - left.probability
  )

  const scrollableClass = sortedPredictions.length > 10 ? 'max-h-[34rem] overflow-y-auto pr-2' : ''

  return (
    <section className="rounded-3xl border border-slate-200 bg-white shadow-xl shadow-slate-200/60">
      <div className="border-b border-slate-200 px-6 py-4 sm:px-8">
        <h2 className="text-xl font-semibold text-slate-900">
          All Antibiotic Susceptibility Estimates for {organism}
        </h2>
      </div>

      <div className={`px-6 py-6 sm:px-8 ${scrollableClass}`}>
        <div className="space-y-4">
          {sortedPredictions.map((item) => {
            const percentage = item.probability * 100
            const isNotRecommended = percentage < 30

            return (
              <div key={item.antibiotic} className="grid grid-cols-[180px_minmax(0,1fr)_72px] items-center gap-4">
                <div className="truncate text-sm font-medium text-slate-800">
                  {item.antibiotic}
                </div>

                <div className="relative h-4 overflow-hidden rounded-full bg-slate-100">
                  <div
                    className={`h-full rounded-full transition-all duration-500 ${getBarClass(item.probability)}`}
                    style={{ width: `${Math.max(percentage, 2)}%` }}
                  />
                </div>

                <div className="flex flex-col items-end text-right text-sm">
                  <span className="font-semibold text-slate-700">{percentage.toFixed(1)}%</span>
                  {isNotRecommended && (
                    <span className="text-xs font-medium text-slate-400">Not recommended for this organism</span>
                  )}
                </div>
              </div>
            )
          })}
        </div>
      </div>
    </section>
  )
}