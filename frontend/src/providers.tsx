import { type QueryClient, QueryClientProvider } from '@tanstack/react-query'
import type { ReactNode } from 'react'

import { ToastProvider } from './components/ui/Toast'
import { UserProvider } from './user/UserProvider'

/** Everything the app needs except the router (tests supply a MemoryRouter). */
export function Providers({ client, children }: { client: QueryClient; children: ReactNode }) {
  return (
    <QueryClientProvider client={client}>
      <ToastProvider>
        <UserProvider>{children}</UserProvider>
      </ToastProvider>
    </QueryClientProvider>
  )
}
