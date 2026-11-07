import type { ReactNode } from 'react'

import type { UserRole } from '../../api/types'
import { useActingUser } from '../../user/userContext'
import { Button, ButtonLink } from '../ui/Button'
import { Card } from '../ui/Card'
import { EmptyState, Spinner } from '../ui/feedback'

const ROLE_NAME: Record<UserRole, string> = { BUYER: 'buyer', SUPPLIER: 'supplier' }

/** Shows `children` only to the given role, and offers a one-click switch otherwise. */
export function RequireRole({ role, action, children }: { role: UserRole; action: string; children: ReactNode }) {
  const { user, users, isLoading, setUserId } = useActingUser()

  if (isLoading) return <Spinner label="Loading users" className="mt-10" />
  if (user?.role === role) return <>{children}</>

  const candidate = users.find((u) => u.role === role)
  return (
    <Card className="mx-auto max-w-xl">
      <EmptyState
        title={`Only a ${ROLE_NAME[role]} can ${action}`}
        description={
          user
            ? `You're acting as ${user.company_name} (${ROLE_NAME[user.role]}). Switch user to continue.`
            : 'Choose who you are acting as to continue.'
        }
        action={
          <>
            {candidate && (
              <Button onClick={() => setUserId(candidate.id)}>Act as {candidate.company_name}</Button>
            )}
            <ButtonLink to="/" variant="ghost">
              Back to auctions
            </ButtonLink>
          </>
        }
      />
    </Card>
  )
}
