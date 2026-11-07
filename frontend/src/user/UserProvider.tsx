/**
 * The "acting as" user. There is no login: the seeded users come from `GET /api/users`, the
 * choice is kept in localStorage, and every request sends it as `X-User-Id`.
 */
import { useQuery } from '@tanstack/react-query'
import { useCallback, useLayoutEffect, useMemo, useState, type ReactNode } from 'react'

import { setActingUserId } from '../api/client'
import { api, queryKeys } from '../api/endpoints'
import { STORAGE_KEY, UserContext, type UserContextValue } from './userContext'

function readStoredId(): string | null {
  try {
    return window.localStorage.getItem(STORAGE_KEY)
  } catch {
    return null
  }
}

function storeId(id: string): void {
  try {
    window.localStorage.setItem(STORAGE_KEY, id)
  } catch {
    // Private mode or blocked storage: the choice lasts for this tab only.
  }
}

export function UserProvider({ children }: { children: ReactNode }) {
  const query = useQuery({ queryKey: queryKeys.users, queryFn: api.users, staleTime: Infinity })
  const [storedId, setStoredId] = useState(readStoredId)

  const users = useMemo(() => query.data?.items ?? [], [query.data])
  // A stored id can be stale after a reseed: fall back to the first buyer.
  const user =
    users.find((u) => u.id === storedId) ?? users.find((u) => u.role === 'BUYER') ?? users[0] ?? null

  // Before children's effects run, so their requests already carry the right header.
  useLayoutEffect(() => {
    setActingUserId(user?.id ?? null)
  }, [user?.id])

  const setUserId = useCallback((id: string) => {
    setStoredId(id)
    storeId(id)
  }, [])

  const { refetch } = query
  const retry = useCallback(() => void refetch(), [refetch])

  const value = useMemo<UserContextValue>(
    () => ({ user, users, isLoading: query.isPending, error: query.error, retry, setUserId }),
    [user, users, query.isPending, query.error, retry, setUserId],
  )
  return <UserContext.Provider value={value}>{children}</UserContext.Provider>
}
