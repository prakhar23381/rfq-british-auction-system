import { formatTime } from '../lib/format'
import { cx } from './ui/cx'

interface ScheduleTimelineProps {
  startMs: number
  /** Current close (moves with extensions). */
  closeMs: number
  forcedMs: number
  windowMinutes: number
  /** Optional "now" marker. */
  nowMs?: number
  className?: string
}

const iso = (ms: number) => new Date(ms).toISOString()

const POINTS = [
  { name: 'Start', tone: 'text-ink-2', swatch: 'bg-peri', align: '', justify: '' },
  { name: 'Close', tone: 'text-ink', swatch: 'bg-amber', align: 'text-center', justify: 'justify-center' },
  {
    name: 'Forced',
    tone: 'text-ink-2',
    swatch: 'bg-[repeating-linear-gradient(135deg,var(--color-amber)_0_2px,transparent_2px_4px)]',
    align: 'text-right',
    justify: 'justify-end',
  },
] as const

/**
 * Start → forced close as one bar: bidding time (periwinkle), the trigger window just before
 * the close (amber), and the room extensions can use up to the forced close (hatched).
 */
export function ScheduleTimeline({ startMs, closeMs, forcedMs, windowMinutes, nowMs, className }: ScheduleTimelineProps) {
  const span = forcedMs - startMs
  if (!(span > 0) || closeMs <= startMs || closeMs > forcedMs) return null
  const pct = (ms: number) => `${(Math.min(Math.max(ms - startMs, 0), span) / span) * 100}%`
  const windowStart = Math.max(closeMs - windowMinutes * 60_000, startMs)

  const label =
    `Bidding ${formatTime(iso(startMs))} to ${formatTime(iso(closeMs))}, ` +
    `trigger window from ${formatTime(iso(windowStart))}, ` +
    `extensions possible until ${formatTime(iso(forcedMs))}`

  return (
    <div className={className}>
      <div role="img" aria-label={label} className="relative h-3 rounded-full bg-white/[0.05]">
        <span
          className="absolute inset-y-0 left-0 rounded-l-full bg-gradient-to-r from-peri/50 to-peri"
          style={{ width: pct(closeMs) }}
        />
        <span
          className="absolute inset-y-0 bg-amber/80"
          style={{ left: pct(windowStart), width: `calc(${pct(closeMs)} - ${pct(windowStart)})` }}
        />
        <span
          className="absolute inset-y-0 right-0 rounded-r-full bg-[repeating-linear-gradient(135deg,rgb(255_184_107/0.28)_0_4px,transparent_4px_8px)]"
          style={{ left: pct(closeMs) }}
        />
        <span aria-hidden className="absolute -inset-y-1 w-0.5 rounded bg-ink" style={{ left: pct(closeMs) }} />
        {nowMs !== undefined && nowMs >= startMs && nowMs <= forcedMs && (
          <span aria-hidden className="absolute -inset-y-1.5 w-px bg-mint shadow-[0_0_6px] shadow-mint" style={{ left: pct(nowMs) }} />
        )}
      </div>
      <dl className="mt-3 grid grid-cols-3 gap-2 font-mono text-[11px]">
        {POINTS.map((point) => (
          <div key={point.name} className={point.align}>
            <dt className={cx('flex items-center gap-1.5 text-ink-3 uppercase', point.justify)}>
              <span aria-hidden className={cx('size-2 rounded-sm', point.swatch)} />
              {point.name}
            </dt>
            <dd className={cx('mt-0.5', point.tone)}>
              {formatTime(iso({ Start: startMs, Close: closeMs, Forced: forcedMs }[point.name]))}
            </dd>
          </div>
        ))}
      </dl>
    </div>
  )
}
