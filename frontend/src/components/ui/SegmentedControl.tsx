import type { KeyboardEvent } from 'react'

import { cx } from './cx'

export interface Segment<T extends string> {
  value: T
  label: string
  count?: number
  /** Small colour dot before the label. */
  dot?: string
}

interface SegmentedControlProps<T extends string> {
  label: string
  segments: Segment<T>[]
  value: T
  onChange: (value: T) => void
  className?: string
}

/** Radio-group style filter tabs. Arrow keys move between options. */
export function SegmentedControl<T extends string>({
  label,
  segments,
  value,
  onChange,
  className,
}: SegmentedControlProps<T>) {
  const onKeyDown = (event: KeyboardEvent<HTMLDivElement>) => {
    const step = event.key === 'ArrowRight' ? 1 : event.key === 'ArrowLeft' ? -1 : 0
    if (!step) return
    event.preventDefault()
    const index = segments.findIndex((segment) => segment.value === value)
    const next = segments[(index + step + segments.length) % segments.length]
    onChange(next.value)
    const buttons = event.currentTarget.querySelectorAll<HTMLButtonElement>('[role="radio"]')
    buttons[segments.indexOf(next)]?.focus()
  }

  return (
    <div
      role="radiogroup"
      aria-label={label}
      onKeyDown={onKeyDown}
      className={cx(
        'flex max-w-full gap-0.5 overflow-x-auto rounded-[10px] border border-[rgb(190_170_255/0.1)] bg-[rgb(170_150_255/0.07)] p-[3px] [scrollbar-width:none]',
        className,
      )}
    >
      {segments.map((segment) => {
        const checked = segment.value === value
        return (
          <button
            key={segment.value}
            type="button"
            role="radio"
            aria-checked={checked}
            tabIndex={checked ? 0 : -1}
            onClick={() => onChange(segment.value)}
            className={cx(
              'flex shrink-0 items-center gap-2 rounded-[7px] px-3 py-1.5 text-[13px] whitespace-nowrap transition-colors',
              checked ? 'bg-white/10 text-ink shadow-[inset_0_1px_0_rgb(255_255_255/0.06)]' : 'text-ink-2 hover:text-ink',
            )}
          >
            {segment.dot && <span aria-hidden className={cx('size-1.5 rounded-full', segment.dot)} />}
            {segment.label}
            {segment.count !== undefined && (
              <span className={cx('font-mono text-[11px]', checked ? 'text-ink-2' : 'text-ink-3')}>
                {segment.count}
              </span>
            )}
          </button>
        )
      })}
    </div>
  )
}
