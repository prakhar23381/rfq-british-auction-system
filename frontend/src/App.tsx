import { Route, Routes } from 'react-router'

import { Layout } from './components/layout/Layout'
import { RequireRole } from './components/layout/RequireRole'
import { AuctionDetailPage } from './pages/AuctionDetailPage'
import { AuctionListPage } from './pages/AuctionListPage'
import { CreateRfqPage } from './pages/CreateRfqPage'
import { NotFoundPage } from './pages/NotFoundPage'

export function App() {
  return (
    <Routes>
      <Route element={<Layout />}>
        <Route index element={<AuctionListPage />} />
        <Route
          path="rfqs/new"
          element={
            <RequireRole role="BUYER" action="create an RFQ">
              <CreateRfqPage />
            </RequireRole>
          }
        />
        <Route path="rfqs/:id" element={<AuctionDetailPage />} />
        <Route path="*" element={<NotFoundPage />} />
      </Route>
    </Routes>
  )
}
