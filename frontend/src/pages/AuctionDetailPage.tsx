import { useParams } from 'react-router'

import { ButtonLink } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { EmptyState } from '../components/ui/feedback'
import { PageHeader } from '../components/ui/PageHeader'
import { useDocumentTitle } from '../hooks/useDocumentTitle'

/** Stage 11 fills this in (R14–R17). */
export function AuctionDetailPage() {
  const { id } = useParams()
  useDocumentTitle('Auction')
  return (
    <>
      <PageHeader eyebrow="Auction" title="Auction details" />
      <Card surface="panel">
        <EmptyState
          title="Auction details"
          description={<>The ranking, bid form and activity log for <span className="font-mono">{id}</span> are built in Stage 11.</>}
          action={
            <ButtonLink to="/" variant="ghost">
              Back to auctions
            </ButtonLink>
          }
        />
      </Card>
    </>
  )
}
