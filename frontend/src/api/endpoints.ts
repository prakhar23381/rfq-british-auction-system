import { request } from './client'
import type {
  ActivityList,
  AuctionStatus,
  BidCreate,
  BidList,
  BidSubmitResponse,
  Health,
  RfqCreate,
  RfqDetail,
  RfqListResponse,
  UserList,
} from './types'

export interface ListParams {
  status?: AuctionStatus
  search?: string
  page?: number
  pageSize?: number
}

/** TanStack Query keys, one place so live events can patch the right cache entries. */
export const queryKeys = {
  users: ['users'] as const,
  health: ['health'] as const,
  rfqs: ['rfqs'] as const,
  rfqLists: ['rfqs', 'list'] as const,
  rfqList: (params: ListParams) => ['rfqs', 'list', params] as const,
  rfq: (id: string) => ['rfqs', 'detail', id] as const,
  activity: (id: string) => ['rfqs', 'activity', id] as const,
  bidHistory: (id: string) => ['rfqs', 'bids', id] as const,
}

export const api = {
  health: () => request<Health>('/api/health'),
  users: () => request<UserList>('/api/users'),

  listRfqs: ({ status, search, page, pageSize }: ListParams = {}) =>
    request<RfqListResponse>('/api/rfqs', {
      query: { status, search, page, page_size: pageSize },
    }),
  getRfq: (id: string) => request<RfqDetail>(`/api/rfqs/${encodeURIComponent(id)}`),
  createRfq: (body: RfqCreate) => request<RfqDetail>('/api/rfqs', { method: 'POST', body }),

  bidHistory: (id: string) =>
    request<BidList>(`/api/rfqs/${encodeURIComponent(id)}/bids`, { query: { history: true } }),
  submitBid: (id: string, body: BidCreate) =>
    request<BidSubmitResponse>(`/api/rfqs/${encodeURIComponent(id)}/bids`, {
      method: 'POST',
      body,
    }),

  activity: (id: string, beforeId?: number, limit = 50) =>
    request<ActivityList>(`/api/rfqs/${encodeURIComponent(id)}/activity`, {
      query: { before_id: beforeId, limit },
    }),
}
