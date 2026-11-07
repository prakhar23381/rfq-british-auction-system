import { useEffect, useState } from 'react'
import { useSearchParams } from 'react-router'

import type { ListParams } from '../api/endpoints'
import { errorMessage } from '../api/errors'
import type { AuctionStatus } from '../api/types'
import { Button, ButtonLink } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { cx } from '../components/ui/cx'
import { EmptyState, ErrorState, Skeleton } from '../components/ui/feedback'
import { Accent, PageHeader } from '../components/ui/PageHeader'
import { Pagination } from '../components/ui/Pagination'
import { SearchInput } from '../components/ui/SearchInput'
import { type Segment, SegmentedControl } from '../components/ui/SegmentedControl'
import { AuctionTable } from '../features/listing/AuctionTable'
import { useLiveListing } from '../features/listing/useLiveListing'
import { useDebouncedValue } from '../hooks/useDebouncedValue'
import { useDocumentTitle } from '../hooks/useDocumentTitle'
import { STATUS_LABELS } from '../lib/format'
import { useActingUser } from '../user/userContext'

export const PAGE_SIZE = 20
const SEARCH_DEBOUNCE_MS = 300

type Filter = AuctionStatus | 'ALL'

const FILTERS: Array<{ value: Filter; dot?: string }> = [
  { value: 'ALL' },
  { value: 'ACTIVE', dot: 'bg-mint' },
  { value: 'SCHEDULED', dot: 'bg-lilac' },
  { value: 'CLOSED', dot: 'bg-peri-2' },
  { value: 'FORCE_CLOSED', dot: 'bg-rose' },
]

function parseStatus(value: string | null): AuctionStatus | undefined {
  return value && value in STATUS_LABELS ? (value as AuctionStatus) : undefined
}

function parsePage(value: string | null): number {
  const page = Number(value)
  return Number.isInteger(page) && page > 1 ? page : 1
}

export function AuctionListPage() {
  const { user } = useActingUser()
  const [params, setParams] = useSearchParams()
  const status = parseStatus(params.get('status'))
  const page = parsePage(params.get('page'))
  const urlSearch = params.get('search') ?? ''

  // The box updates instantly; the URL (and the request) follow after a pause in typing.
  const [searchInput, setSearchInput] = useState(urlSearch)
  const debouncedSearch = useDebouncedValue(searchInput.trim(), SEARCH_DEBOUNCE_MS)
  useEffect(() => {
    // The URL changed elsewhere (a sidebar link, back button): show its search.
    setSearchInput((current) => (current.trim() === urlSearch ? current : urlSearch))
  }, [urlSearch])
  useEffect(() => {
    if (debouncedSearch === urlSearch) return
    setParams(
      (current) => {
        const next = new URLSearchParams(current)
        if (debouncedSearch) next.set('search', debouncedSearch)
        else next.delete('search')
        next.delete('page')
        return next
      },
      { replace: true },
    )
    // Only a new debounced value should write to the URL.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [debouncedSearch])

  const updateParams = (changes: Record<string, string | null>) =>
    setParams((current) => {
      const next = new URLSearchParams(current)
      for (const [key, value] of Object.entries(changes)) {
        if (value === null) next.delete(key)
        else next.set(key, value)
      }
      return next
    })

  const listParams: ListParams = { status, search: urlSearch || undefined, page, pageSize: PAGE_SIZE }
  const { query, items, updated, onDue } = useLiveListing(listParams)
  const counts = query.data?.status_counts
  const totalAll = counts ? Object.values(counts).reduce((sum, n) => sum + n, 0) : undefined

  const label = status ? STATUS_LABELS[status] : null
  useDocumentTitle(label ? `${label} auctions` : 'Auctions')

  const segments: Segment<Filter>[] = FILTERS.map(({ value, dot }) => ({
    value,
    dot,
    label: value === 'ALL' ? 'All' : STATUS_LABELS[value],
    count: value === 'ALL' ? totalAll : counts?.[value],
  }))

  const isBuyer = user?.role === 'BUYER'
  const filtered = Boolean(status || urlSearch)
  const clearFilters = () => {
    setSearchInput('')
    setParams(new URLSearchParams())
  }

  let body
  if (query.isPending) {
    body = (
      <Card surface="panel" bodyClassName="p-0">
        <div aria-label="Loading auctions" role="status">
          {Array.from({ length: 5 }, (_, i) => (
            <div key={i} className="flex items-center gap-6 border-b border-line-soft px-5 py-5 last:border-0">
              <Skeleton className="h-4 w-48" />
              <Skeleton className="ml-auto h-4 w-20" />
              <Skeleton className="hidden h-4 w-24 sm:block" />
              <Skeleton className="hidden h-6 w-16 sm:block" />
            </div>
          ))}
        </div>
      </Card>
    )
  } else if (query.isError && !query.data) {
    body = (
      <Card surface="panel">
        <ErrorState title="Couldn’t load auctions" message={errorMessage(query.error)} onRetry={() => void query.refetch()} />
      </Card>
    )
  } else if (items.length === 0) {
    body = (
      <Card surface="panel">
        {filtered ? (
          <EmptyState
            title="No auctions match"
            description={
              urlSearch
                ? `Nothing ${label ? `${label.toLowerCase()} ` : ''}matches “${urlSearch}”.`
                : `There are no ${label?.toLowerCase()} auctions right now.`
            }
            action={
              <Button variant="ghost" onClick={clearFilters}>
                Clear filters
              </Button>
            }
          />
        ) : (
          <EmptyState
            title="No auctions yet"
            description={
              isBuyer
                ? 'Create an RFQ to start a British auction. It shows up here for every supplier, live.'
                : 'When a buyer creates an RFQ it appears here, live.'
            }
            action={isBuyer && <ButtonLink to="/rfqs/new">Create the first RFQ</ButtonLink>}
          />
        )}
      </Card>
    )
  } else {
    body = (
      <>
        <AuctionTable
          items={items}
          updated={updated}
          onDue={onDue}
          className={cx('transition-opacity', query.isPlaceholderData && 'opacity-60')}
        />
        <Pagination
          page={page}
          pageSize={PAGE_SIZE}
          total={query.data?.total ?? 0}
          onChange={(next) => updateParams({ page: next > 1 ? String(next) : null })}
        />
      </>
    )
  }

  return (
    <>
      <PageHeader
        eyebrow={label ? `Auctions · ${label}` : 'Auctions'}
        title={
          <>
            British <Accent>auctions</Accent>
          </>
        }
        description="Every RFQ with its lowest bid, current close time and status, updated live."
        actions={isBuyer && <ButtonLink to="/rfqs/new">Create RFQ</ButtonLink>}
      />

      <div className="mb-4 flex flex-col gap-3 md:flex-row md:items-center">
        <SegmentedControl
          label="Filter by status"
          segments={segments}
          value={status ?? 'ALL'}
          onChange={(value) => updateParams({ status: value === 'ALL' ? null : value, page: null })}
          className="self-start"
        />
        <SearchInput
          value={searchInput}
          onChange={setSearchInput}
          label="Search auctions"
          placeholder="Search name or reference"
          className="md:ml-auto md:w-72"
        />
      </div>

      {body}
    </>
  )
}
