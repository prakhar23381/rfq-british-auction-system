import { ApiError } from './client'

/** Backend error codes → what the user should read. */
const MESSAGES: Record<string, string> = {
  UNAUTHENTICATED: 'Choose who you are acting as (top right) and try again.',
  FORBIDDEN: 'Your current role can’t do that. Switch user under “Acting as”.',
  NOT_FOUND: 'That auction doesn’t exist.',
  DUPLICATE_REFERENCE: 'That reference ID is already used by another RFQ.',
  AUCTION_NOT_STARTED: 'Bidding hasn’t opened yet.',
  AUCTION_CLOSED: 'Bidding has closed for this auction.',
  FORCED_CLOSE_NOT_AFTER_CLOSE: 'The forced close must be later than the bid close time.',
  BID_NOT_LOWER: 'Your new bid must be lower than your previous bid.',
  VALIDATION_ERROR: 'Some fields need attention.',
  INTERNAL_ERROR: 'Something went wrong on the server. Please try again.',
  NETWORK_ERROR: 'Can’t reach the server. Check that the API is running.',
}

export function errorMessage(error: unknown): string {
  if (error instanceof ApiError) return MESSAGES[error.code] ?? error.message
  if (error instanceof Error && error.message) return error.message
  return 'Something went wrong.'
}
