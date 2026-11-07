import { Card } from '../components/ui/Card'
import { EmptyState } from '../components/ui/feedback'
import { Accent, PageHeader } from '../components/ui/PageHeader'
import { useDocumentTitle } from '../hooks/useDocumentTitle'

/** Stage 10 fills this in (R1–R5). Wrapped in <RequireRole role="BUYER"> by the router. */
export function CreateRfqPage() {
  useDocumentTitle('Create RFQ')
  return (
    <>
      <PageHeader
        eyebrow="New RFQ"
        title={
          <>
            Create a British <Accent>auction</Accent>
          </>
        }
        description="Set the bidding schedule and how late bids extend the auction."
      />
      <Card>
        <EmptyState title="RFQ form" description="The create form is built in Stage 10." />
      </Card>
    </>
  )
}
