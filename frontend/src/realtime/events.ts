/** Server → client WebSocket messages (docs/API.md, "WebSocket"). */
import type {
  Activity,
  AuctionStatus,
  Bid,
  Extension,
  RankedBid,
  RfqListItem,
  RfqOut,
  RfqStats,
} from '../api/types'

export const LISTING_CHANNEL = 'listing'

export function rfqChannel(rfqId: string): string {
  return `rfq:${rfqId}`
}

export interface BidSubmittedData {
  version: number
  bid: Bid
  rank: number
  rank_label: string
  extension: Extension | null
  rfq: RfqOut
  ranking: RankedBid[]
  stats: RfqStats
  activity: Activity[]
}

export interface AuctionExtendedData {
  version: number
  previous_close_at: string
  new_close_at: string
  capped: boolean
  reason: string
  extension_count: number
  activity: Activity[]
}

export interface AuctionStatusData {
  version: number
  status: AuctionStatus
  rfq: RfqOut
  activity: Activity[]
}

export interface ListingItemData {
  version: number
  item: RfqListItem
}

export interface ErrorData {
  code: string
  message: string
}

type Message<T extends string, D> = {
  type: T
  channel: string | null
  data: D
  server_time: string
}

export type ServerEvent =
  | Message<'bid.submitted', BidSubmittedData>
  | Message<'auction.extended', AuctionExtendedData>
  | Message<'auction.status', AuctionStatusData>
  | Message<'listing.updated', ListingItemData>
  | Message<'rfq.created', ListingItemData>
  | Message<'subscribed' | 'unsubscribed' | 'pong' | 'resync', Record<string, never>>
  | Message<'error', ErrorData>

export type ClientMessage =
  | { action: 'subscribe' | 'unsubscribe'; channel: string }
  | { action: 'ping' }
