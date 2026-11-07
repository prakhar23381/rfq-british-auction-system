import type { TriggerType } from '../../api/types'
import { cx } from '../../components/ui/cx'
import { formatTime } from '../../lib/format'
import type { ParsedTimes } from './form'

interface Option {
  value: TriggerType
  title: string
  description: (x: string) => string
  example: (at: string, newClose: string) => string
}

const OPTIONS: Option[] = [
  {
    value: 'BID_RECEIVED',
    title: 'Bid received',
    description: (x) => `Any new bid in the last ${x} extends the auction.`,
    example: (at, newClose) => `A bid at ${at} moves the close to ${newClose}.`,
  },
  {
    value: 'ANY_RANK_CHANGE',
    title: 'Any rank change',
    description: (x) => `Extends when a bid in the last ${x} changes any supplier’s rank (L1, L2, L3…).`,
    example: (at, newClose) => `At ${at} B underbids A, the ranks swap, and the close moves to ${newClose}.`,
  },
  {
    value: 'L1_CHANGE',
    title: 'Lowest bidder (L1) changes',
    description: (x) => `Extends only when a bid in the last ${x} changes who is L1.`,
    example: (at, newClose) => `At ${at} C becomes the new L1 and the close moves to ${newClose}. A bid that stays L2 doesn’t extend.`,
  },
]

const time = (ms: number) => formatTime(new Date(ms).toISOString())

interface TriggerTypeCardsProps {
  value: TriggerType
  onChange: (value: TriggerType) => void
  times: ParsedTimes
  error?: string
}

/** The three extension triggers as radio cards, with examples using the form's own times. */
export function TriggerTypeCards({ value, onChange, times, error }: TriggerTypeCardsProps) {
  const { close, forced, windowMinutes: x, extensionMinutes: y } = times
  const example =
    close !== null && x !== null && y !== null
      ? {
          at: time(close - Math.max(1, Math.floor(x / 2)) * 60_000),
          newClose: time(forced !== null ? Math.min(close + y * 60_000, forced) : close + y * 60_000),
        }
      : null
  const xLabel = x !== null ? `${x} min` : 'X min'

  return (
    <fieldset aria-describedby={error ? 'rfq-triggerType-error' : undefined}>
      <legend className="mb-2 text-[13px] font-medium text-ink-2">What extends the auction?</legend>
      <div className="grid gap-2.5 md:grid-cols-3">
        {OPTIONS.map((option) => {
          const checked = option.value === value
          return (
            <label
              key={option.value}
              className={cx(
                'relative flex cursor-pointer flex-col gap-2 rounded-xl border p-4 transition-colors',
                'has-[:focus-visible]:outline-2 has-[:focus-visible]:outline-offset-2 has-[:focus-visible]:outline-peri-2',
                checked
                  ? 'border-peri-2/70 bg-peri/12 shadow-[inset_0_1px_0_rgb(255_255_255/0.06)]'
                  : 'border-[rgb(190_170_255/0.14)] bg-white/[0.02] hover:border-[rgb(190_170_255/0.3)]',
              )}
            >
              <input
                type="radio"
                name="triggerType"
                value={option.value}
                checked={checked}
                onChange={() => onChange(option.value)}
                className="peer sr-only"
              />
              <span className="flex items-center gap-2.5">
                <span
                  aria-hidden
                  className={cx(
                    'grid size-4 shrink-0 place-items-center rounded-full border',
                    checked ? 'border-peri-2' : 'border-ink-3',
                  )}
                >
                  {checked && <span className="size-2 rounded-full bg-peri-2" />}
                </span>
                <span className="text-sm font-medium text-ink">{option.title}</span>
              </span>
              <span className="text-[13px] leading-snug text-ink-2">{option.description(xLabel)}</span>
              {example && (
                <span className="mt-auto border-t border-line-soft pt-2 text-xs leading-snug text-ink-3">
                  <span className="font-mono text-[10px] tracking-[0.08em] uppercase">e.g. </span>
                  {option.example(example.at, example.newClose)}
                </span>
              )}
            </label>
          )
        })}
      </div>
      {error && (
        <p id="rfq-triggerType-error" className="mt-1.5 text-xs text-danger">
          {error}
        </p>
      )}
    </fieldset>
  )
}
