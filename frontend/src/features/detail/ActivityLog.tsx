import type { Activity, ActivityType } from '../../api/types'
import { Button } from '../../components/ui/Button'
import { Card } from '../../components/ui/Card'
import { Chip } from '../../components/ui/Chip'
import { cx } from '../../components/ui/cx'
import { Spinner } from '../../components/ui/feedback'
import { DateTime } from '../../components/ui/values'
import { formatTime } from '../../lib/format'

const STYLE: Record<ActivityType, { label: string; dot: string }> = {
  RFQ_CREATED: { label: 'Created', dot: 'bg-lilac' },
  AUCTION_STARTED: { label: 'Opened', dot: 'bg-mint' },
  BID_SUBMITTED: { label: 'Bid', dot: 'bg-peri-2' },
  AUCTION_EXTENDED: { label: 'Extended', dot: 'bg-amber shadow-[0_0_8px] shadow-amber' },
  EXTENSION_SKIPPED: { label: 'No extension', dot: 'border border-amber bg-transparent' },
  AUCTION_CLOSED: { label: 'Closed', dot: 'bg-peri' },
  AUCTION_FORCE_CLOSED: { label: 'Force closed', dot: 'bg-rose' },
}

function meta(entry: Activity, key: string): unknown {
  return (entry.metadata as Record<string, unknown>)[key]
}

function Entry({ entry }: { entry: Activity }) {
  const style = STYLE[entry.type]
  const extended = entry.type === 'AUCTION_EXTENDED'
  const previous = meta(entry, 'previous_close_at')
  const next = meta(entry, 'new_close_at')
  return (
    <li className="relative flex gap-3 pb-5 pl-1 last:pb-0">
      <span aria-hidden className="absolute top-3 bottom-0 left-[8.5px] w-px bg-line [li:last-child>&]:hidden" />
      <span aria-hidden className={cx('relative mt-1.5 size-2.5 shrink-0 rounded-full', style.dot)} />
      <div className="min-w-0 flex-1">
        <div className="flex flex-wrap items-center gap-x-2 gap-y-1">
          <span className={cx('font-mono text-[11px] tracking-[0.04em] uppercase', extended ? 'text-amber' : 'text-ink-3')}>
            {style.label}
          </span>
          <DateTime value={entry.created_at} format="time" className="font-mono text-[11px] text-ink-3" />
          {entry.actor && <span className="text-[11px] text-ink-3">· {entry.actor.company_name}</span>}
          {extended && meta(entry, 'capped') === true && <Chip tone="amber">capped</Chip>}
        </div>
        <p className="mt-1 text-[13px] leading-relaxed text-ink-2">{entry.message}</p>
        {extended && typeof previous === 'string' && typeof next === 'string' && (
          <p className="mt-1 font-mono text-xs text-amber">
            {formatTime(previous)} → {formatTime(next)}
          </p>
        )}
      </div>
    </li>
  )
}

interface ActivityLogProps {
  entries: Activity[]
  isPending: boolean
  hasMore: boolean
  loadingMore: boolean
  onLoadMore: () => void
}

/** Bids, extensions (with their reason) and open/close, newest first (R17). */
export function ActivityLog({ entries, isPending, hasMore, loadingMore, onLoadMore }: ActivityLogProps) {
  return (
    <Card title="Activity">
      {isPending ? (
        <Spinner label="Loading activity" />
      ) : (
        <ol aria-label="Activity log">
          {entries.map((entry) => (
            <Entry key={entry.id} entry={entry} />
          ))}
        </ol>
      )}
      {hasMore && (
        <Button variant="subtle" size="sm" className="mt-5" onClick={onLoadMore} disabled={loadingMore}>
          {loadingMore ? 'Loading…' : 'Load older activity'}
        </Button>
      )}
    </Card>
  )
}
