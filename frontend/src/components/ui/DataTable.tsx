import type { ReactNode } from 'react'

import { cx } from './cx'

export interface Column<T> {
  key: string
  header: ReactNode
  cell: (row: T) => ReactNode
  align?: 'left' | 'right'
  className?: string
  /** On phones each row becomes a card: the `primary` column is its title… */
  primary?: boolean
  /** …and the others are label/value pairs (`false` hides the column there). */
  mobileLabel?: string | false
}

interface DataTableProps<T> {
  caption: string
  columns: Column<T>[]
  rows: T[]
  rowKey: (row: T) => string
  rowClassName?: (row: T) => string | undefined
  className?: string
}

/** A table on wider screens; a stack of cards below 640px (no horizontal page scroll). */
export function DataTable<T>({
  caption,
  columns,
  rows,
  rowKey,
  rowClassName,
  className,
}: DataTableProps<T>) {
  const primary = columns.find((column) => column.primary)
  const details = columns.filter((column) => !column.primary && column.mobileLabel !== false)

  return (
    <div className={cx('panel overflow-hidden rounded-2xl', className)}>
      <div className="hidden overflow-x-auto sm:block">
        <table className="w-full border-collapse text-[13px] text-ink-2">
          <caption className="sr-only">{caption}</caption>
          <thead>
            <tr className="bg-[rgb(70_52_160/0.18)]">
              {columns.map((column) => (
                <th
                  key={column.key}
                  scope="col"
                  className={cx(
                    'px-4 py-3 font-mono text-[10.5px] font-normal tracking-[0.06em] whitespace-nowrap text-ink-3 uppercase',
                    column.align === 'right' ? 'text-right' : 'text-left',
                  )}
                >
                  {column.header}
                </th>
              ))}
            </tr>
          </thead>
          <tbody>
            {rows.map((row) => (
              <tr
                key={rowKey(row)}
                className={cx(
                  'border-t border-[rgb(190_170_255/0.07)] transition-colors hover:bg-white/[0.025]',
                  rowClassName?.(row),
                )}
              >
                {columns.map((column) => (
                  <td
                    key={column.key}
                    className={cx(
                      'px-4 py-3 align-middle',
                      column.align === 'right' && 'text-right',
                      column.className,
                    )}
                  >
                    {column.cell(row)}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      </div>

      <ul className="divide-y divide-[rgb(190_170_255/0.07)] sm:hidden" aria-label={caption}>
        {rows.map((row) => (
          <li key={rowKey(row)} className={cx('px-4 py-4', rowClassName?.(row))}>
            {primary && <div className="mb-3 text-sm text-ink">{primary.cell(row)}</div>}
            <dl className="grid grid-cols-2 gap-x-4 gap-y-3 text-[13px] text-ink-2">
              {details.map((column) => (
                <div key={column.key} className="min-w-0">
                  <dt className="font-mono text-[10px] tracking-[0.06em] text-ink-3 uppercase">
                    {column.mobileLabel ?? column.header}
                  </dt>
                  <dd className="mt-1 break-words">{column.cell(row)}</dd>
                </div>
              ))}
            </dl>
          </li>
        ))}
      </ul>
    </div>
  )
}
