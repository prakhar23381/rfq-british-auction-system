import type { ReactNode } from 'react'

import { cx } from './cx'

export type ChipTone = 'plain' | 'mint' | 'amber' | 'peri' | 'rose' | 'lilac' | 'danger'

const TONES: Record<ChipTone, { chip: string; dot: string }> = {
  plain: { chip: 'text-ink-2 bg-[rgb(170_150_255/0.1)] border-[rgb(190_170_255/0.12)]', dot: 'bg-ink-3' },
  mint: { chip: 'text-mint-2 bg-mint/10 border-mint/20', dot: 'bg-mint shadow-[0_0_8px] shadow-mint' },
  amber: { chip: 'text-amber bg-amber/10 border-amber/25', dot: 'bg-amber shadow-[0_0_8px] shadow-amber' },
  peri: { chip: 'text-peri-2 bg-peri/12 border-peri/25', dot: 'bg-peri-2' },
  rose: { chip: 'text-rose bg-rose/10 border-rose/25', dot: 'bg-rose' },
  lilac: { chip: 'text-lilac bg-lilac/10 border-lilac/20', dot: 'bg-lilac' },
  danger: { chip: 'text-danger bg-danger/10 border-danger/25', dot: 'bg-danger' },
}

interface ChipProps {
  tone?: ChipTone
  /** Show a dot before the label; `pulse` makes it a live indicator. */
  dot?: boolean | 'pulse'
  className?: string
  title?: string
  children: ReactNode
}

export function Chip({ tone = 'plain', dot = false, className, title, children }: ChipProps) {
  const styles = TONES[tone]
  return (
    <span
      title={title}
      className={cx(
        'inline-flex h-6 shrink-0 items-center gap-1.5 rounded-md border px-2 font-mono text-[11px] tracking-[0.02em] whitespace-nowrap',
        styles.chip,
        className,
      )}
    >
      {dot && (
        <span
          aria-hidden
          className={cx('size-1.5 rounded-full', styles.dot, dot === 'pulse' && 'animate-live')}
        />
      )}
      {children}
    </span>
  )
}
