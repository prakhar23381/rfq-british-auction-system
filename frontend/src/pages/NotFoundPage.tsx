import { ButtonLink } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { EmptyState } from '../components/ui/feedback'
import { useDocumentTitle } from '../hooks/useDocumentTitle'

export function NotFoundPage() {
  useDocumentTitle('Page not found')
  return (
    <Card className="mx-auto mt-6 max-w-xl">
      <EmptyState
        icon={<span className="font-mono text-4xl font-light text-peri-2">404</span>}
        title="This page doesn’t exist"
        description="The link may be wrong, or the page has moved."
        action={<ButtonLink to="/">Go to auctions</ButtonLink>}
      />
    </Card>
  )
}
