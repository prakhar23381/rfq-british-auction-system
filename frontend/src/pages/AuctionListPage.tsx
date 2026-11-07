import { useSearchParams } from 'react-router'

import type { AuctionStatus } from '../api/types'
import { ButtonLink } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { EmptyState } from '../components/ui/feedback'
import { Accent, PageHeader } from '../components/ui/PageHeader'
import { useDocumentTitle } from '../hooks/useDocumentTitle'
import { STATUS_LABELS } from '../lib/format'
import { useActingUser } from '../user/userContext'

/** Stage 9 fills this in (R12, R13). */
export function AuctionListPage() {
  const { user } = useActingUser()
  const [params] = useSearchParams()
  const status = params.get('status') as AuctionStatus | null
  const label = status && status in STATUS_LABELS ? STATUS_LABELS[status] : null
  useDocumentTitle(label ? `${label} auctions` : 'Auctions')

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
        actions={user?.role === 'BUYER' && <ButtonLink to="/rfqs/new">Create RFQ</ButtonLink>}
      />
      <Card surface="panel">
        <EmptyState title="Auction listing" description="The live auction table is built in Stage 9." />
      </Card>
    </>
  )
}
