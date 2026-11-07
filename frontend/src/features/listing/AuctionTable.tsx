import { Link } from 'react-router'

import type { RfqListItem } from '../../api/types'
import { Chip } from '../../components/ui/Chip'
import { type Column, DataTable } from '../../components/ui/DataTable'
import { StatusBadge } from '../../components/ui/StatusBadge'
import { Countdown, DateTime, Money } from '../../components/ui/values'
import { formatDateTime } from '../../lib/format'

function ExtensionChip({ item }: { item: RfqListItem }) {
  if (item.extension_count === 0) return null
  const times = item.extension_count === 1 ? 'once' : `${item.extension_count} times`
  return (
    <Chip tone="amber" title={`Extended ${times}. Original close: ${formatDateTime(item.bid_close_at)}`}>
      +{item.extension_count} ext
    </Chip>
  )
}

function CloseCell({ item, onDue }: { item: RfqListItem; onDue: () => void }) {
  if (item.status === 'ACTIVE') {
    return (
      <div className="flex flex-col gap-1">
        <div className="flex items-center gap-2">
          <Countdown
            target={item.current_close_at}
            windowMinutes={item.trigger_window_minutes ?? undefined}
            overLabel="Closing…"
            onOver={onDue}
            className="text-[15px]"
          />
          <ExtensionChip item={item} />
        </div>
        <span className="text-xs text-ink-3">
          closes <DateTime value={item.current_close_at} format="time" />
        </span>
      </div>
    )
  }
  if (item.status === 'SCHEDULED') {
    return (
      <div className="flex flex-col gap-1">
        <DateTime value={item.current_close_at} className="text-ink-2" />
        <span className="text-xs text-ink-3">
          opens in <Countdown target={item.bid_start_at} overLabel="opening…" onOver={onDue} className="text-xs text-ink-2" />
        </span>
      </div>
    )
  }
  return (
    <div className="flex flex-col items-start gap-1">
      <DateTime value={item.current_close_at} className="text-ink-2" />
      <ExtensionChip item={item} />
    </div>
  )
}

interface AuctionTableProps {
  items: RfqListItem[]
  /** RFQs changed by a live event: their rows flash when the version changes. */
  updated: ReadonlySet<string>
  onDue: () => void
  className?: string
}

export function AuctionTable({ items, updated, onDue, className }: AuctionTableProps) {
  const columns: Column<RfqListItem>[] = [
    {
      key: 'rfq',
      header: 'RFQ',
      primary: true,
      cell: (item) => (
        <div className="flex min-w-0 items-start justify-between gap-3">
          <div className="min-w-0">
            <Link
              to={`/rfqs/${item.id}`}
              className="font-medium text-ink decoration-peri-2/60 underline-offset-4 transition-colors hover:text-peri-2 hover:underline"
            >
              {item.name}
            </Link>
            <p className="mt-0.5 font-mono text-[11px] text-ink-3">{item.reference_id}</p>
          </div>
          <span className="sm:hidden">
            <StatusBadge status={item.status} />
          </span>
        </div>
      ),
      className: 'max-w-72',
    },
    {
      key: 'lowest',
      header: 'Lowest bid',
      align: 'right',
      cell: (item) =>
        item.lowest_bid ? (
          <div className="flex flex-col sm:items-end">
            <Money amount={item.lowest_bid.amount} currency={item.lowest_bid.currency} className="text-[14px] text-mint-2" />
            <span className="max-w-40 truncate text-xs text-ink-3">{item.lowest_bid.supplier_name}</span>
          </div>
        ) : (
          <span className="text-ink-3">No bids yet</span>
        ),
    },
    {
      key: 'bids',
      header: 'Bids',
      align: 'right',
      cell: (item) => (
        <div className="flex flex-col font-mono sm:items-end">
          <span className="text-ink">{item.bid_count}</span>
          <span className="text-[11px] text-ink-3">
            {item.supplier_count} {item.supplier_count === 1 ? 'supplier' : 'suppliers'}
          </span>
        </div>
      ),
    },
    { key: 'close', header: 'Bid close', cell: (item) => <CloseCell item={item} onDue={onDue} /> },
    {
      key: 'forced',
      header: 'Forced close',
      cell: (item) => <DateTime value={item.forced_close_at} className="text-ink-2" />,
    },
    {
      key: 'status',
      header: 'Status',
      mobileLabel: false,
      cell: (item) => <StatusBadge status={item.status} />,
    },
  ]

  return (
    <DataTable
      caption="British auctions"
      columns={columns}
      rows={items}
      // The version in the key remounts a row when it changes, which replays the flash.
      rowKey={(item) => `${item.id}:${item.version}`}
      rowClassName={(item) => (updated.has(item.id) ? 'animate-flash' : undefined)}
      className={className}
    />
  )
}
