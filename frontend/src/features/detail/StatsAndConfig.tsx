import type { ReactNode } from 'react'

import type { AuctionConfig, RfqStats } from '../../api/types'
import { Card } from '../../components/ui/Card'
import { Money } from '../../components/ui/values'
import { formatMinutes } from '../../lib/auctionPreview'
import { TRIGGER_LABELS } from '../../lib/format'

function Tile({ label, value, note }: { label: string; value: ReactNode; note?: ReactNode }) {
  return (
    <div className="rounded-xl border border-line-soft bg-[rgb(70_52_160/0.22)] px-4 py-3.5">
      <p className="text-xs text-ink-3">{label}</p>
      <p className="mt-1 font-mono text-[22px] leading-tight text-ink tabular-nums">{value}</p>
      {note && <p className="mt-1 truncate text-[11px] text-ink-3">{note}</p>}
    </div>
  )
}

/** Bids, suppliers, extensions and savings vs the first L1 (the business goal in §1.4). */
export function StatsStrip({ stats }: { stats: RfqStats }) {
  const savings = stats.savings_pct !== null ? Number(stats.savings_pct) : null
  return (
    <div className="grid grid-cols-2 gap-3 md:grid-cols-4">
      <Tile label="Bids" value={stats.bid_count} note={stats.bid_count > 0 ? 'including revisions' : 'none yet'} />
      <Tile label="Suppliers" value={stats.supplier_count} />
      <Tile
        label="Extensions"
        value={<span className={stats.extension_count > 0 ? 'text-amber' : undefined}>{stats.extension_count}</span>}
        note={stats.extension_count > 0 ? `+${formatMinutes(stats.total_extended_minutes)} in total` : undefined}
      />
      <Tile
        label="Savings vs first L1"
        value={savings !== null ? <span className={savings > 0 ? 'text-mint-2' : undefined}>{savings.toFixed(1)}%</span> : '—'}
        note={
          stats.first_l1_amount && stats.current_l1_amount ? (
            <>
              <Money amount={stats.first_l1_amount} /> → <Money amount={stats.current_l1_amount} />
            </>
          ) : undefined
        }
      />
    </div>
  )
}

const TRIGGER_EXPLANATION = {
  BID_RECEIVED: 'Any new bid inside the window extends the close.',
  ANY_RANK_CHANGE: 'A bid inside the window extends the close when it changes any supplier’s rank.',
  L1_CHANGE: 'A bid inside the window extends the close only when it changes who is L1.',
} as const

/** X, Y and the trigger type (R16). */
export function ConfigCard({ config }: { config: AuctionConfig }) {
  return (
    <Card title="Auction settings">
      <dl className="grid grid-cols-2 gap-4">
        <div>
          <dt className="text-xs text-ink-3">Trigger window (X)</dt>
          <dd className="mt-1 font-mono text-lg text-amber">{config.trigger_window_minutes} min</dd>
        </div>
        <div>
          <dt className="text-xs text-ink-3">Extension (Y)</dt>
          <dd className="mt-1 font-mono text-lg text-amber">+{config.extension_duration_minutes} min</dd>
        </div>
        <div className="col-span-2">
          <dt className="text-xs text-ink-3">Trigger</dt>
          <dd className="mt-1 text-sm text-ink">{TRIGGER_LABELS[config.trigger_type]}</dd>
          <dd className="mt-1 text-xs leading-relaxed text-ink-3">
            {TRIGGER_EXPLANATION[config.trigger_type]} Watched during the last {config.trigger_window_minutes} min before
            the close; never past the forced close.
          </dd>
        </div>
      </dl>
    </Card>
  )
}
