/** Bid form: values, validation mirroring the backend, request body, server error mapping. */
import type { ApiError } from '../../api/client'
import type { BidCreate, RankedBid } from '../../api/types'
import { centsToAmount, toCents } from '../../lib/money'

export interface BidFormValues {
  carrierName: string
  freight: string
  origin: string
  destination: string
  transitDays: string
  validityDate: string
  notes: string
}

/** `total` holds errors about the sum (zero, or not lower than the current bid). */
export type BidField = keyof BidFormValues | 'total'
export type BidErrors = Partial<Record<BidField, string>>

export const BID_FIELD_ORDER: BidField[] = ['carrierName', 'freight', 'origin', 'destination', 'total', 'transitDays', 'validityDate', 'notes']
export const bidFieldId = (field: BidField) => `bid-${field}`

/** Starts from the supplier's current bid (they only need to lower a charge), or empty. */
export function initialBidValues(previous: RankedBid | undefined, pickupDate: string): BidFormValues {
  if (previous) {
    return {
      carrierName: previous.carrier_name,
      freight: String(Number(previous.freight_charges)),
      origin: String(Number(previous.origin_charges)),
      destination: String(Number(previous.destination_charges)),
      transitDays: String(previous.transit_time_days),
      validityDate: previous.quote_validity_date,
      notes: '',
    }
  }
  return { carrierName: '', freight: '', origin: '0', destination: '0', transitDays: '', validityDate: pickupDate, notes: '' }
}

/** Total in paise, or null while any charge is invalid. */
export function totalCents(values: BidFormValues): number | null {
  const parts = [values.freight, values.origin, values.destination].map(toCents)
  return parts.every((part) => part !== null) ? (parts as number[]).reduce((a, b) => a + b, 0) : null
}

const AMOUNT_MESSAGE = 'Enter an amount like 12500 or 12500.50.'
/** The server stores totals as NUMERIC(14, 2). */
export const MAX_TOTAL_CENTS = 99_999_999_999_999

export function validateBid(values: BidFormValues, opts: { pickupDate: string; previousTotal: string | null }): BidErrors {
  const errors: BidErrors = {}
  const carrier = values.carrierName.trim()
  if (carrier.length < 2) errors.carrierName = carrier ? 'Use at least 2 characters.' : 'Enter the carrier or shipping line.'
  else if (carrier.length > 100) errors.carrierName = 'Use at most 100 characters.'

  for (const field of ['freight', 'origin', 'destination'] as const) {
    if (toCents(values[field]) === null) errors[field] = values[field].trim() ? AMOUNT_MESSAGE : 'Enter an amount (0 if none).'
  }
  const total = totalCents(values)
  if (total !== null) {
    if (total <= 0) errors.total = 'The total must be more than zero.'
    else if (total > MAX_TOTAL_CENTS) errors.total = 'The total must be at most ₹9,99,99,99,99,999.99.'
    else if (opts.previousTotal !== null) {
      const previous = toCents(opts.previousTotal)
      if (previous !== null && total >= previous) errors.total = 'Your new total must be lower than your current bid.'
    }
  }

  const days = values.transitDays.trim()
  if (!/^\d{1,3}$/.test(days) || Number(days) < 1 || Number(days) > 365) errors.transitDays = 'Enter whole days from 1 to 365.'

  if (!/^\d{4}-\d{2}-\d{2}$/.test(values.validityDate)) errors.validityDate = 'Choose until when the quote is valid.'
  else if (values.validityDate < opts.pickupDate) errors.validityDate = 'The quote must be valid on the pickup date or later.'

  if (values.notes.length > 500) errors.notes = 'Use at most 500 characters.'
  return errors
}

/** Request body; call only with values that passed `validateBid`. */
export function toBidPayload(values: BidFormValues): BidCreate {
  const cents = (value: string) => {
    const parsed = toCents(value)
    if (parsed === null) throw new Error('toBidPayload called with invalid values')
    return centsToAmount(parsed)
  }
  const notes = values.notes.trim()
  return {
    carrier_name: values.carrierName.trim(),
    freight_charges: cents(values.freight),
    origin_charges: cents(values.origin),
    destination_charges: cents(values.destination),
    transit_time_days: Number(values.transitDays),
    quote_validity_date: values.validityDate,
    notes: notes || null,
  }
}

const SERVER_FIELDS: Record<string, BidField> = {
  carrier_name: 'carrierName',
  freight_charges: 'freight',
  origin_charges: 'origin',
  destination_charges: 'destination',
  transit_time_days: 'transitDays',
  quote_validity_date: 'validityDate',
  notes: 'notes',
}

/** Field errors from the server; BID_NOT_LOWER and zero totals belong to the total. */
export function bidServerErrors(error: ApiError): BidErrors {
  const errors: BidErrors = {}
  if (error.code === 'BID_NOT_LOWER') errors.total = error.message
  for (const detail of error.details) {
    const field = detail.field ? SERVER_FIELDS[detail.field] : undefined
    if (field) errors[field] ??= detail.message
    else if (detail.message.toLowerCase().includes('total')) errors.total ??= detail.message
  }
  return errors
}
