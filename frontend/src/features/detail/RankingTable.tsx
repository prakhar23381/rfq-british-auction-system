import { useQuery } from '@tanstack/react-query'
import { Fragment, useState } from 'react'

import { api, queryKeys } from '../../api/endpoints'
import type { RankedBid } from '../../api/types'
import { Chip } from '../../components/ui/Chip'
import { cx } from '../../components/ui/cx'
import { EmptyState, Spinner } from '../../components/ui/feedback'
import { DateTime, Money } from '../../components/ui/values'

function RankChip({ row }: { row: RankedBid }) {
  return (
    <Chip tone={row.rank === 1 ? 'mint' : 'plain'} className="w-10 justify-center">
      {row.rank_label}
    </Chip>
  )
}

function History({ rfqId, supplierId }: { rfqId: string; supplierId: string }) {
  const { data, isPending, isError } = useQuery({
    queryKey: queryKeys.bidHistory(rfqId),
    queryFn: () => api.bidHistory(rfqId),
  })
  if (isPending) return <Spinner label="Loading bid history" />
  if (isError) return <p className="text-xs text-danger">Couldn’t load the history.</p>
  const bids = data.items.filter((bid) => bid.supplier.id === supplierId)
  return (
    <ol className="space-y-1.5" aria-label="Bid history">
      {bids.map((bid, index) => (
        <li key={bid.id} className="flex flex-wrap items-center gap-x-4 gap-y-1 text-xs text-ink-2">
          <DateTime value={bid.submitted_at} format="time" className="font-mono text-ink-3" />
          <Money amount={bid.total_amount} currency={bid.currency} className={index === 0 ? 'text-ink' : 'text-ink-3 line-through'} />
          <span>{bid.carrier_name}</span>
          {bid.rank_at_submission !== null && <span className="text-ink-3">was L{bid.rank_at_submission} when placed</span>}
        </li>
      ))}
    </ol>
  )
}

interface RankingTableProps {
  rfqId: string
  ranking: RankedBid[]
  /** The acting supplier, whose row is highlighted. */
  meId?: string
  changed: ReadonlySet<string>
}

/** Every supplier's latest bid, lowest total first (R14, R15). */
export function RankingTable({ rfqId, ranking, meId, changed }: RankingTableProps) {
  const [open, setOpen] = useState<string | null>(null)
  if (ranking.length === 0) {
    return (
      <div className="panel rounded-2xl">
        <EmptyState title="No bids yet" description="Bids appear here the moment suppliers place them, ranked by total price." />
      </div>
    )
  }

  const rowClass = (row: RankedBid) =>
    cx(
      changed.has(row.supplier.id) && 'animate-flash',
      row.supplier.id === meId && 'bg-peri/[0.08] shadow-[inset_2px_0_0] shadow-peri-2',
    )
  // Re-key a row when it changes, so its flash replays.
  const key = (row: RankedBid) => `${row.supplier.id}:${row.bid_id}:${row.rank}`
  const toggle = (supplierId: string) => setOpen((current) => (current === supplierId ? null : supplierId))
  const historyButton = (row: RankedBid) => (
    <button
      type="button"
      onClick={() => toggle(row.supplier.id)}
      aria-expanded={open === row.supplier.id}
      className="rounded-md px-2 py-1 font-mono text-[11px] text-ink-3 transition-colors hover:bg-white/5 hover:text-ink"
    >
      {row.revision_count} {row.revision_count === 1 ? 'bid' : 'bids'} {open === row.supplier.id ? '▴' : '▾'}
    </button>
  )
  const supplier = (row: RankedBid) => (
    <span className="flex items-center gap-2">
      <span className="truncate text-ink">{row.supplier.company_name}</span>
      {row.supplier.id === meId && <Chip tone="peri">You</Chip>}
    </span>
  )

    // Table or cards by the space this panel actually gets (it shares the row with the bid form),
  // not by the window width.
  return (
    <div className="@container panel overflow-hidden rounded-2xl">
      <div className="hidden overflow-x-auto @2xl:block">
        <table className="w-full border-collapse text-[13px] text-ink-2">
          <caption className="sr-only">Supplier ranking, lowest total first</caption>
          <thead>
            <tr className="bg-[rgb(70_52_160/0.18)] text-left font-mono text-[10.5px] tracking-[0.06em] whitespace-nowrap text-ink-3 uppercase">
              <th scope="col" className="px-3 py-3 font-normal">Rank</th>
              <th scope="col" className="px-3 py-3 font-normal">Supplier</th>
              <th scope="col" className="px-3 py-3 text-right font-normal">Freight</th>
              <th scope="col" className="hidden px-2.5 py-3 text-right font-normal @4xl:table-cell">Origin</th>
              <th scope="col" className="hidden px-2.5 py-3 text-right font-normal @4xl:table-cell"><abbr title="Destination" className="no-underline">Dest.</abbr></th>
              <th scope="col" className="px-3 py-3 text-right font-normal">Total</th>
              <th scope="col" className="px-2.5 py-3 font-normal">Transit</th>
              <th scope="col" className="px-3 py-3 font-normal">Submitted</th>
            </tr>
          </thead>
          <tbody>
            {ranking.map((row) => (
              <Fragment key={key(row)}>
                <tr className={cx('border-t border-[rgb(190_170_255/0.07)]', rowClass(row))}>
                  <td className="px-3 py-3"><RankChip row={row} /></td>
                  <td className="max-w-44 px-3 py-3 @4xl:max-w-52">
                    {supplier(row)}
                    <span className="mt-0.5 block truncate text-xs text-ink-3">{row.carrier_name}</span>
                  </td>
                  <td className="px-3 py-3 text-right whitespace-nowrap">
                    <Money amount={row.freight_charges} currency={row.currency} />
                    {/* Narrow tables (e.g. beside the bid form) fold origin and destination in here. */}
                    <span className="mt-0.5 block text-[11px] text-ink-3 @4xl:hidden">
                      + <span className="sr-only">origin </span><Money amount={row.origin_charges} currency={row.currency} />
                      {' + '}<span className="sr-only">destination </span><Money amount={row.destination_charges} currency={row.currency} />
                    </span>
                  </td>
                  <td className="hidden px-2.5 py-3 text-right @4xl:table-cell"><Money amount={row.origin_charges} currency={row.currency} /></td>
                  <td className="hidden px-2.5 py-3 text-right @4xl:table-cell"><Money amount={row.destination_charges} currency={row.currency} /></td>
                  <td className="px-3 py-3 text-right">
                    <Money amount={row.total_amount} currency={row.currency} className={cx('text-[14px]', row.rank === 1 ? 'text-mint-2' : 'text-ink')} />
                  </td>
                  <td className="px-3 py-3 whitespace-nowrap">
                    <span className="font-mono">{row.transit_time_days} d</span>
                    <span className="mt-0.5 block text-[11px] text-ink-3">
                      valid till <DateTime value={row.quote_validity_date} format="date" />
                    </span>
                  </td>
                  <td className="px-3 py-2 whitespace-nowrap">
                    <DateTime value={row.submitted_at} format="time" className="block pl-2 font-mono" />
                    {historyButton(row)}
                  </td>
                </tr>
                {open === row.supplier.id && (
                  <tr className="bg-black/10">
                    <td colSpan={8} className="px-6 py-3">
                      <History rfqId={rfqId} supplierId={row.supplier.id} />
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>

      <ul className="divide-y divide-[rgb(190_170_255/0.07)] @2xl:hidden" aria-label="Supplier ranking">
        {ranking.map((row) => (
          <li key={key(row)} className={cx('px-4 py-4', rowClass(row))}>
            <div className="flex items-center gap-3">
              <RankChip row={row} />
              <div className="min-w-0 flex-1 text-sm">{supplier(row)}</div>
              <Money amount={row.total_amount} currency={row.currency} className={cx('text-[15px]', row.rank === 1 ? 'text-mint-2' : 'text-ink')} />
            </div>
            <dl className="mt-3 grid grid-cols-3 gap-x-3 gap-y-2 text-xs">
              {[
                ['Carrier', row.carrier_name],
                ['Freight', <Money key="f" amount={row.freight_charges} />],
                ['Origin', <Money key="o" amount={row.origin_charges} />],
                ['Destination', <Money key="d" amount={row.destination_charges} />],
                ['Transit', `${row.transit_time_days} d`],
                ['Valid till', <DateTime key="v" value={row.quote_validity_date} format="date" />],
              ].map(([label, value]) => (
                <div key={label as string} className="min-w-0">
                  <dt className="font-mono text-[10px] text-ink-3 uppercase">{label}</dt>
                  <dd className="mt-0.5 truncate text-ink-2">{value}</dd>
                </div>
              ))}
            </dl>
            <div className="mt-2 flex items-center justify-between text-xs text-ink-3">
              <span>
                at <DateTime value={row.submitted_at} format="time" className="font-mono" />
              </span>
              {historyButton(row)}
            </div>
            {open === row.supplier.id && (
              <div className="mt-2 rounded-lg bg-black/10 p-3">
                <History rfqId={rfqId} supplierId={row.supplier.id} />
              </div>
            )}
          </li>
        ))}
      </ul>
    </div>
  )
}
