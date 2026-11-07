import { useParams } from 'react-router'

import { ApiError } from '../api/client'
import { errorMessage } from '../api/errors'
import { ButtonLink } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { EmptyState, ErrorState, Skeleton } from '../components/ui/feedback'
import { BidPanel } from '../features/bid/BidPanel'
import { ActivityLog } from '../features/detail/ActivityLog'
import { AuctionHeader } from '../features/detail/AuctionHeader'
import { RankingTable } from '../features/detail/RankingTable'
import { ConfigCard, StatsStrip } from '../features/detail/StatsAndConfig'
import { useLiveAuction } from '../features/detail/useLiveAuction'
import { useDocumentTitle } from '../hooks/useDocumentTitle'
import { useActingUser } from '../user/userContext'

export function AuctionDetailPage() {
  const { id = '' } = useParams()
  return <AuctionDetail key={id} id={id} />
}

function AuctionDetail({ id }: { id: string }) {
  const { user } = useActingUser()
  const { detail, activity, changedSuppliers, extensionPulse, onDue } = useLiveAuction(id)
  useDocumentTitle(detail.data?.rfq.name ?? 'Auction')

  if (detail.isPending) {
    return (
      <div role="status" aria-label="Loading auction" className="space-y-6">
        <Skeleton className="h-52 rounded-2xl" />
        <Skeleton className="h-20 rounded-2xl" />
        <Skeleton className="h-64 rounded-2xl" />
      </div>
    )
  }
  if (detail.isError) {
    const missing = detail.error instanceof ApiError && (detail.error.status === 404 || detail.error.status === 422)
    return (
      <Card className="mx-auto mt-6 max-w-xl">
        {missing ? (
          <EmptyState
            title="This auction doesn’t exist"
            description="The link may be wrong, or the auction was removed."
            action={<ButtonLink to="/">Go to auctions</ButtonLink>}
          />
        ) : (
          <ErrorState title="Couldn’t load this auction" message={errorMessage(detail.error)} onRetry={() => void detail.refetch()} />
        )}
      </Card>
    )
  }

  const data = detail.data
  const entries = activity.data?.pages.flatMap((page) => page.items) ?? []

  return (
    <div className="space-y-6">
      <AuctionHeader detail={data} extensionPulse={extensionPulse} onDue={onDue} />
      <StatsStrip stats={data.stats} />
      <div className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_360px] lg:items-start">
        <div className="min-w-0 space-y-6">
          <section aria-labelledby="ranking-heading">
            <div className="mb-3 flex items-baseline justify-between">
              <h2 id="ranking-heading" className="text-lg font-normal tracking-tight text-ink">
                Ranking
              </h2>
              <span className="text-xs text-ink-3">Latest bid per supplier, lowest total first</span>
            </div>
            <RankingTable
              rfqId={id}
              ranking={data.ranking}
              meId={user?.role === 'SUPPLIER' ? user.id : undefined}
              changed={changedSuppliers}
            />
          </section>
          <ActivityLog
            entries={entries}
            isPending={activity.isPending}
            hasMore={activity.hasNextPage}
            loadingMore={activity.isFetchingNextPage}
            onLoadMore={() => void activity.fetchNextPage()}
          />
        </div>
        <div className="space-y-6 lg:sticky lg:top-24">
          <BidPanel detail={data} />
          <ConfigCard config={data.auction_config} />
        </div>
      </div>
    </div>
  )
}
