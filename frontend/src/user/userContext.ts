import { createContext, useContext } from 'react'

import type { User } from '../api/types'

export const STORAGE_KEY = 'acting-user-id'

export interface UserContextValue {
  user: User | null
  users: User[]
  isLoading: boolean
  error: unknown
  retry: () => void
  setUserId: (id: string) => void
}

export const UserContext = createContext<UserContextValue | null>(null)

export function useActingUser(): UserContextValue {
  const context = useContext(UserContext)
  if (!context) throw new Error('useActingUser must be used inside <UserProvider>')
  return context
}
