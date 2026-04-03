'use client'

import { ReactNode } from 'react'

type BannerType = 'warning' | 'info' | 'danger'

interface DisclaimerBannerProps {
  message: ReactNode
  type: BannerType
}

const bannerStyles: Record<BannerType, { wrapper: string; icon: string }> = {
  warning: {
    wrapper: 'border-amber-200 bg-amber-50 text-amber-900',
    icon: 'bg-amber-100 text-amber-700',
  },
  info: {
    wrapper: 'border-blue-200 bg-blue-50 text-blue-900',
    icon: 'bg-blue-100 text-blue-700',
  },
  danger: {
    wrapper: 'border-rose-200 bg-rose-50 text-rose-900',
    icon: 'bg-rose-100 text-rose-700',
  },
}

const bannerIcons: Record<BannerType, string> = {
  warning: '⚠',
  info: 'ℹ',
  danger: '⛔',
}

export default function DisclaimerBanner({ message, type }: DisclaimerBannerProps) {
  const styles = bannerStyles[type]

  return (
    <div className={`border px-4 py-3 ${styles.wrapper}`}>
      <div className="mx-auto flex max-w-7xl items-start gap-3 text-sm">
        <span className={`inline-flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-base font-semibold ${styles.icon}`}>
          {bannerIcons[type]}
        </span>
        <div className="leading-6">{message}</div>
      </div>
    </div>
  )
}