import type { ReactNode } from 'react'

import { cx } from './cx'

interface CardProps {
  /** `glass` for headers and forms, `panel` (more opaque) for tables and dense numbers. */
  surface?: 'glass' | 'panel'
  title?: ReactNode
  actions?: ReactNode
  className?: string
  bodyClassName?: string
  children: ReactNode
}

export function Card({
  surface = 'glass',
  title,
  actions,
  className,
  bodyClassName,
  children,
}: CardProps) {
  return (
    <section className={cx(surface, 'relative overflow-hidden rounded-2xl', className)}>
      <span
        aria-hidden
        className="pointer-events-none absolute inset-x-[10%] top-0 h-px bg-gradient-to-r from-transparent via-[rgb(200_180_255/0.6)] to-transparent"
      />
      {(title || actions) && (
        <header className="flex flex-wrap items-center gap-3 border-b border-line-soft px-5 py-4">
          {title && <h2 className="text-sm font-medium text-ink-2">{title}</h2>}
          {actions && <div className="ml-auto flex items-center gap-2">{actions}</div>}
        </header>
      )}
      <div className={cx('p-5', bodyClassName)}>{children}</div>
    </section>
  )
}

/** Small uppercase mono label, used for group headings and table headers. */
export function Eyebrow({ children, className }: { children: ReactNode; className?: string }) {
  return (
    <p className={cx('font-mono text-[11px] tracking-[0.1em] text-ink-3 uppercase', className)}>
      {children}
    </p>
  )
}
