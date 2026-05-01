'use client'

import { ARMDResultCardProps } from '@/types'

const RANK_COLORS = {
  1: { gradient: 'from-emerald-500 to-green-600',  badge: 'bg-emerald-50 text-emerald-700 ring-emerald-200' },
  2: { gradient: 'from-blue-500 to-cyan-600',      badge: 'bg-blue-50   text-blue-700   ring-blue-200'    },
  3: { gradient: 'from-indigo-500 to-purple-600',  badge: 'bg-indigo-50 text-indigo-700 ring-indigo-200'  },
} as const

const ROUTE_STYLE: Record<string, string> = {
  IV: 'bg-red-50 text-red-700 ring-red-200',
  PO: 'bg-green-50 text-green-700 ring-green-200',
  IM: 'bg-amber-50 text-amber-700 ring-amber-200',
}

function getProbLabel(prob: number): { label: string; className: string } {
  if (prob >= 0.85) return { label: 'Highly Susceptible', className: 'bg-emerald-100 text-emerald-800' }
  if (prob >= 0.70) return { label: 'Susceptible',        className: 'bg-blue-100 text-blue-800'       }
  if (prob >= 0.50) return { label: 'Moderate',           className: 'bg-amber-100 text-amber-800'     }
  return                   { label: 'Resistant',           className: 'bg-rose-100 text-rose-800'       }
}

function getProbBarColor(prob: number): string {
  if (prob >= 0.80) return 'from-emerald-400 to-green-500'
  if (prob >= 0.60) return 'from-blue-400 to-cyan-500'
  if (prob >= 0.40) return 'from-amber-400 to-orange-400'
  return 'from-red-400 to-rose-500'
}

export default function ResultCardV2({ recommendation, rank }: ARMDResultCardProps) {
  const colors = RANK_COLORS[rank as 1 | 2 | 3] ?? RANK_COLORS[3]
  const probLabel = getProbLabel(recommendation.probability)
  const routeStyle = ROUTE_STYLE[recommendation.route] ?? 'bg-gray-50 text-gray-700 ring-gray-200'
  const pct = (recommendation.probability * 100).toFixed(1)

  return (
    <div className="bg-white rounded-xl shadow-lg overflow-hidden hover:shadow-xl transition-shadow flex flex-col">
      {/* Header */}
      <div className={`bg-gradient-to-r ${colors.gradient} px-4 py-3 flex items-center justify-between`}>
        <div>
          <p className="text-white/70 text-xs font-medium uppercase tracking-widest">
            Rank #{rank}
          </p>
          <h3 className="text-lg font-bold text-white capitalize">{recommendation.antibiotic}</h3>
        </div>
        <span className={`text-xs font-semibold px-2 py-1 rounded-full ring-1 ${colors.badge}`}>
          #{rank}
        </span>
      </div>

      {/* Body */}
      <div className="p-5 flex flex-col gap-4 flex-1">
        {/* Probability */}
        <div>
          <div className="flex items-end justify-between mb-1">
            <span className="text-sm text-gray-500 font-medium">Susceptibility</span>
            <span className="text-2xl font-bold text-gray-800">{pct}%</span>
          </div>
          <div className="w-full h-2.5 bg-gray-100 rounded-full overflow-hidden">
            <div
              className={`h-full rounded-full bg-gradient-to-r ${getProbBarColor(recommendation.probability)} transition-all`}
              style={{ width: `${pct}%` }}
            />
          </div>
          <div className="mt-2 flex justify-end">
            <span className={`text-xs font-semibold px-2 py-0.5 rounded-full ${probLabel.className}`}>
              {probLabel.label}
            </span>
          </div>
        </div>

        {/* Dosage block */}
        <div className="rounded-xl bg-gray-50 p-4 space-y-3 border border-gray-100">
          <p className="text-xs font-semibold uppercase tracking-widest text-gray-400">Dosage</p>

          <div className="flex items-center justify-between">
            <span className="text-sm text-gray-500">Dose</span>
            <span className="text-sm font-semibold text-gray-800">{recommendation.dose_range}</span>
          </div>

          <div className="flex items-center justify-between">
            <span className="text-sm text-gray-500">Route</span>
            <span className={`text-xs font-bold px-3 py-1 rounded-full ring-1 ${routeStyle}`}>
              {recommendation.route}
            </span>
          </div>

          {recommendation.dose_source !== 'lookup' && (
            <p className="text-xs text-gray-400 italic">
              {recommendation.dose_source === 'model'
                ? 'Dosage estimated by ML model (exact match not found)'
                : 'Dosage from standard reference (model not trained)'}
            </p>
          )}
        </div>
      </div>
    </div>
  )
}
