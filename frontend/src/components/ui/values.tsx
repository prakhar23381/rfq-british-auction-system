/** Small display components for money, dates and countdowns. Numbers use Fira Code. */
import { useEffect, useRef } from 'react'

import { useCountdown } from '../../hooks/useCountdown'
import { formatDate, formatDateTime, formatMoney, formatTime } from '../../lib/format'
import { cx } from './cx'

interface MoneyProps {
  amount: string | number | null | undefined
  currency?: string
  fallback?: string
  className?: string
}

export function Money({ amount, currency = 'INR', fallback = '—', className }: MoneyProps) {
  const empty = amount === null || amount === undefined || amount === ''
  return (
    <span className={cx('font-mono tabular-nums', empty && 'text-ink-3', className)}>
      {empty ? fallback : formatMoney(amount, currency)}
    </span>
  )
}

interface DateTimeProps {
  value: string | null | undefined
  /** `datetime` "7 Nov, 18:05 IST" · `time` "18:05" · `date` for calendar dates ("20 Nov 2026"). */
  format?: 'datetime' | 'time' | 'date'
  className?: string
}

export function DateTime({ value, format = 'datetime', className }: DateTimeProps) {
  if (!value) return <span className={cx('text-ink-3', className)}>—</span>
  const text =
    format === 'date' ? formatDate(value) : format === 'time' ? formatTime(value) : formatDateTime(value)
  const title = format === 'date' ? undefined : formatDateTime(value) + ' · ' + value
  return (
    <time dateTime={value} title={title} className={cx('tabular-nums', className)}>
      {text}
    </time>
  )
}

interface CountdownProps {
  target: string | null | undefined
  /** Trigger window X in minutes: inside it the countdown turns amber. */
  windowMinutes?: number
  /** Shown once the target has passed (e.g. "Closing…" until the status event arrives). */
  overLabel?: string
  /** Called once when the countdown reaches zero while mounted. */
  onOver?: () => void
  className?: string
}

export function Countdown({ target, windowMinutes, overLabel, onOver, className }: CountdownProps) {
  const countdown = useCountdown(target, windowMinutes)
  const onOverRef = useRef(onOver)
  useEffect(() => {
    onOverRef.current = onOver
  })
  const wasOver = useRef(countdown.isOver)
  useEffect(() => {
    if (countdown.isOver && !wasOver.current) onOverRef.current?.()
    wasOver.current = countdown.isOver
  }, [countdown.isOver])

  if (countdown.isOver && overLabel) {
    return <span className={cx('font-mono text-ink-3', className)}>{overLabel}</span>
  }
  return (
    <span
      role="timer"
      className={cx(
        'font-mono tabular-nums',
        countdown.isInWindow ? 'text-amber' : 'text-ink',
        countdown.isFinalMinute && 'font-medium',
        className,
      )}
    >
      {countdown.label}
    </span>
  )
}
