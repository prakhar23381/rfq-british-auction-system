/** Friendly names for the generated OpenAPI types (`npm run gen:api` / `make api-types`). */
import type { components } from './schema'

type Schemas = components['schemas']

export type AuctionStatus = Schemas['AuctionStatus']
export type UserRole = Schemas['UserRole']
export type TriggerType = Schemas['TriggerType']
export type ActivityType = Schemas['ActivityType']

export type User = Schemas['UserOut']
export type UserList = Schemas['UserList']
export type Party = Schemas['PartyOut']

export type RfqListItem = Schemas['RfqListItem']
export type RfqListResponse = Schemas['RfqListResponse']
export type RfqDetail = Schemas['RfqDetail']
export type RfqOut = Schemas['RfqOut']
export type RfqCreate = Schemas['RfqCreate']
export type RfqStats = Schemas['RfqStats']
export type AuctionConfig = Schemas['AuctionConfigOut']

export type RankedBid = Schemas['RankedBidOut']
export type Bid = Schemas['BidOut']
export type BidList = Schemas['BidListResponse']
export type BidCreate = Schemas['BidCreate']
export type BidSubmitResponse = Schemas['BidSubmitResponse']
export type Extension = Schemas['ExtensionOut']

export type Activity = Schemas['ActivityOut']
export type ActivityList = Schemas['ActivityListResponse']

export type Health = Schemas['HealthResponse']
export type ErrorDetail = Schemas['ErrorDetail']
