import type { TriggerType } from '../../api/types'
import { ScheduleTimeline } from '../../components/ScheduleTimeline'
import { formatMinutes, previewSchedule } from '../../lib/auctionPreview'
import { formatDateTime, formatTime } from '../../lib/format'
import type { ParsedTimes } from './form'

const TRIGGER_PHRASE: Record<TriggerType, string> = {
  BID_RECEIVED: 'bid',
  ANY_RANK_CHANGE: 'bid that changes any supplier’s rank',
  L1_CHANGE: 'bid that changes the lowest bidder (L1)',
}

const time = (ms: number) => formatTime(new Date(ms).toISOString())

/** Plain-language summary of what the schedule and settings will do. */
export function SchedulePreview({ times, triggerType }: { times: ParsedTimes; triggerType: TriggerType }) {
  const { start, close, forced, windowMinutes: x, extensionMinutes: y } = times
  const preview =
    start !== null && close !== null && forced !== null && x !== null && y !== null
      ? previewSchedule({ startMs: start, closeMs: close, forcedMs: forced, windowMinutes: x, extensionMinutes: y })
      : null

  if (!preview || start === null || close === null || forced === null || x === null || y === null) {
    return <p className="text-sm text-ink-3">Fix the highlighted fields to see how this auction will run.</p>
  }

  const extensions = preview.maxExtensions === 1 ? '1 extension' : `${preview.maxExtensions} extensions`
  const shortened = preview.lastExtensionMinutes < y

  return (
    <div className="space-y-5">
      <ScheduleTimeline startMs={start} closeMs={close} forcedMs={forced} windowMinutes={x} />
      <ul className="space-y-3 text-[13px] leading-relaxed text-ink-2">
        <li>
          Bidding opens <span className="text-ink">{formatDateTime(new Date(start).toISOString())}</span> and is due
          to close at <span className="text-ink">{time(close)}</span> ({formatMinutes(preview.durationMinutes)}).
        </li>
        <li>
          Monitoring window:{' '}
          <span className="font-mono text-amber">
            {time(preview.windowStartMs)}–{time(close)}
          </span>
          {preview.windowCoversAuction && ' (the whole auction)'}.
        </li>
        <li>
          Each {TRIGGER_PHRASE[triggerType]} in the window moves the close by{' '}
          <span className="font-mono text-amber">{y} min</span>.
        </li>
        <li>
          It can never run past <span className="text-ink">{time(forced)}</span>: at most{' '}
          <span className="text-ink">{extensions}</span>
          {shortened && preview.maxExtensions > 0 && (
            <>, the last one cut to {formatMinutes(preview.lastExtensionMinutes)}</>
          )}
          .
        </li>
      </ul>
    </div>
  )
}
