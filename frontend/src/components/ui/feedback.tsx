import type { ReactNode } from 'react'

import { cx } from './cx'

export function Spinner({ label = 'Loading', className }: { label?: string; className?: string }) {
  return (
    <span role="status" className={cx('inline-flex items-center gap-2 text-ink-3', className)}>
      <svg aria-hidden viewBox="0 0 24 24" className="size-4 animate-spin" fill="none">
        <circle cx="12" cy="12" r="9" stroke="currentColor" strokeOpacity=".25" strokeWidth="2.5" />
        <path d="M21 12a9 9 0 0 0-9-9" stroke="var(--color-peri-2)" strokeWidth="2.5" strokeLinecap="round" />
      </svg>
      <span className="sr-only">{label}</span>
    </span>
  )
}

export function Skeleton({ className }: { className?: string }) {
  return <span aria-hidden className={cx('block animate-pulse rounded-md bg-violet/10', className)} />
}

interface EmptyStateProps {
  icon?: ReactNode
  title: string
  description?: ReactNode
  action?: ReactNode
  className?: string
}

export function EmptyState({ icon, title, description, action, className }: EmptyStateProps) {
  return (
    <div className={cx('flex flex-col items-center px-6 py-14 text-center', className)}>
      {icon && <div className="mb-4 text-ink-3 [&_svg]:size-7">{icon}</div>}
      <h3 className="text-lg font-normal tracking-tight text-ink">{title}</h3>
      {description && <p className="mt-2 max-w-md text-sm leading-relaxed text-ink-2">{description}</p>}
      {action && <div className="mt-6 flex flex-wrap justify-center gap-2">{action}</div>}
    </div>
  )
}

interface ErrorStateProps {
  title?: string
  message: string
  onRetry?: () => void
}

export function ErrorState({ title = 'Couldn’t load this', message, onRetry }: ErrorStateProps) {
  return (
    <div role="alert" className="flex flex-col items-center px-6 py-14 text-center">
      <span aria-hidden className="mb-4 grid size-9 place-items-center rounded-full bg-danger/15 font-mono text-danger">
        !
      </span>
      <h3 className="text-lg font-normal text-ink">{title}</h3>
      <p className="mt-2 max-w-md text-sm text-ink-2">{message}</p>
      {onRetry && (
        <button
          type="button"
          onClick={onRetry}
          className="mt-5 rounded-lg border border-line px-3 py-1.5 text-sm text-ink-2 transition-colors hover:bg-white/5 hover:text-ink"
        >
          Try again
        </button>
      )}
    </div>
  )
}
