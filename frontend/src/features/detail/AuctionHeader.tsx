import type { RfqDetail } from '../../api/types'
import { ScheduleTimeline } from '../../components/ScheduleTimeline'
import { Chip } from '../../components/ui/Chip'
import { cx } from '../../components/ui/cx'
import { StatusBadge } from '../../components/ui/StatusBadge'
import { Countdown, DateTime } from '../../components/ui/values'
import { useServerNow } from '../../hooks/useServerNow'
import { formatDuration } from '../../lib/auctionPreview'
import { formatTime } from '../../lib/format'
import { parseInstant } from '../../lib/time'

interface AuctionHeaderProps {
  detail: RfqDetail
  extensionPulse: number
  onDue: () => void
}

export function AuctionHeader({ detail, extensionPulse, onDue }: AuctionHeaderProps) {
  const { rfq, auction_config: config, stats } = detail
  const live = rfq.status === 'ACTIVE' || rfq.status === 'SCHEDULED'
  const now = useServerNow(live ? 1000 : null)

  return (
    <section className="glass relative overflow-hidden rounded-2xl p-5 sm:p-7">
      <span
        aria-hidden
        className="pointer-events-none absolute inset-x-[10%] top-0 h-px bg-gradient-to-r from-transparent via-[rgb(200_180_255/0.6)] to-transparent"
      />
      <div className="flex flex-wrap items-start gap-x-8 gap-y-5">
        <div className="min-w-0 flex-1">
          <div className="mb-3 flex flex-wrap items-center gap-2">
            <span className="font-mono text-xs text-ink-3">{rfq.reference_id}</span>
            <StatusBadge status={rfq.status} />
            {rfq.extension_count > 0 && (
              <Chip tone="amber">
                +{rfq.extension_count} ext
              </Chip>
            )}
          </div>
          <h1 className="text-[28px] leading-[1.15] font-light tracking-[-0.025em] text-ink sm:text-[36px]">{rfq.name}</h1>
          <p className="mt-2 text-sm text-ink-2">
            {rfq.buyer.company_name} · pickup <DateTime value={rfq.pickup_date} format="date" />
          </p>
        </div>

        <div
          key={extensionPulse}
          className={cx(
            'rounded-xl border border-line px-5 py-3.5 text-right',
            extensionPulse > 0 && 'animate-extend',
          )}
        >
          {rfq.status === 'ACTIVE' && (
            <>
              <p className="font-mono text-[11px] tracking-[0.08em] text-ink-3 uppercase">Closes in</p>
              <Countdown
                target={rfq.current_close_at}
                windowMinutes={config.trigger_window_minutes}
                overLabel="Closing…"
                onOver={onDue}
                className="text-[34px] leading-tight font-light"
              />
            </>
          )}
          {rfq.status === 'SCHEDULED' && (
            <>
              <p className="font-mono text-[11px] tracking-[0.08em] text-ink-3 uppercase">Opens in</p>
              <Countdown target={rfq.bid_start_at} overLabel="Opening…" onOver={onDue} className="text-[34px] leading-tight font-light" />
            </>
          )}
          {(rfq.status === 'CLOSED' || rfq.status === 'FORCE_CLOSED') && (
            <>
              <p className="font-mono text-[11px] tracking-[0.08em] text-ink-3 uppercase">Closed at</p>
              <p className="font-mono text-[34px] leading-tight font-light text-ink">
                {formatTime(rfq.closed_at ?? rfq.current_close_at)}
              </p>
            </>
          )}
        </div>
      </div>

      <p className="mt-6 flex flex-wrap gap-x-2 gap-y-1 text-[13px] text-ink-2">
        <span>
          Original close <span className="font-mono text-ink">{formatTime(rfq.bid_close_at)}</span>
        </span>
        <span aria-hidden className="text-ink-3">·</span>
        {rfq.extension_count > 0 ? (
          <span className="text-amber">
            Extended +{formatDuration(stats.total_extended_seconds)} ({rfq.extension_count}×) to{' '}
            <span className="font-mono">{formatTime(rfq.current_close_at)}</span>
          </span>
        ) : (
          <span>Not extended</span>
        )}
        <span aria-hidden className="text-ink-3">·</span>
        <span>
          Forced close <span className="font-mono text-ink">{formatTime(rfq.forced_close_at)}</span>
        </span>
      </p>

      <ScheduleTimeline
        className="mt-4"
        startMs={parseInstant(rfq.bid_start_at)}
        closeMs={parseInstant(rfq.current_close_at)}
        forcedMs={parseInstant(rfq.forced_close_at)}
        windowMinutes={config.trigger_window_minutes}
        nowMs={live ? now : undefined}
      />
    </section>
  )
}
