/**
 * Create-RFQ form: values as the inputs hold them, client-side validation mirroring the
 * backend rules (docs/API.md), the request body, and mapping of server errors to fields.
 */
import type { ApiError } from '../../api/client'
import type { RfqCreate, TriggerType } from '../../api/types'
import {
  MINUTE,
  ceilToMinute,
  parseLocalInput,
  toLocalDate,
  toLocalInput,
  toUtcDate,
} from '../../lib/datetimeLocal'

export interface RfqFormValues {
  name: string
  referenceId: string
  pickupDate: string
  bidStartAt: string
  bidCloseAt: string
  forcedCloseAt: string
  triggerWindowMinutes: string
  extensionDurationMinutes: string
  triggerType: TriggerType
}

export type FieldName = keyof RfqFormValues
export type FormErrors = Partial<Record<FieldName, string>>

/** Order of the fields on the page (focus goes to the first invalid one). */
export const FIELD_ORDER: FieldName[] = [
  'name',
  'referenceId',
  'pickupDate',
  'bidStartAt',
  'bidCloseAt',
  'forcedCloseAt',
  'triggerWindowMinutes',
  'extensionDurationMinutes',
  'triggerType',
]

export const fieldId = (name: FieldName) => `rfq-${name}`

/** The server allows a start up to a minute in the past (clock drift, slow submit). */
const START_TOLERANCE_MS = MINUTE
const REFERENCE_PATTERN = /^[A-Z0-9-]{3,30}$/
const DAY = 24 * 60 * MINUTE

/** Start in 2 minutes, close 30 minutes later, forced close 30 minutes after that. */
export function defaultValues(nowMs: number): RfqFormValues {
  const start = ceilToMinute(nowMs + 2 * MINUTE)
  const close = start + 30 * MINUTE
  const forced = close + 30 * MINUTE
  return {
    name: '',
    referenceId: '',
    pickupDate: toLocalDate(close + 7 * DAY),
    bidStartAt: toLocalInput(start),
    bidCloseAt: toLocalInput(close),
    forcedCloseAt: toLocalInput(forced),
    triggerWindowMinutes: '10',
    extensionDurationMinutes: '5',
    triggerType: 'L1_CHANGE',
  }
}

/** Moves the whole schedule to a new start, keeping its durations. */
export function shiftSchedule(values: RfqFormValues, newStartMs: number): RfqFormValues {
  const start = parseLocalInput(values.bidStartAt)
  const close = parseLocalInput(values.bidCloseAt)
  const forced = parseLocalInput(values.forcedCloseAt)
  if (!start.ok || !close.ok || !forced.ok) {
    const fresh = defaultValues(newStartMs - 2 * MINUTE)
    return { ...values, bidStartAt: fresh.bidStartAt, bidCloseAt: fresh.bidCloseAt, forcedCloseAt: fresh.forcedCloseAt }
  }
  const delta = newStartMs - start.ms
  return {
    ...values,
    bidStartAt: toLocalInput(newStartMs),
    bidCloseAt: toLocalInput(close.ms + delta),
    forcedCloseAt: toLocalInput(forced.ms + delta),
  }
}

function minutes(value: string): number | null {
  if (!/^\d{1,3}$/.test(value.trim())) return null
  const n = Number(value)
  return n >= 1 && n <= 120 ? n : null
}

export interface ParsedTimes {
  start: number | null
  close: number | null
  forced: number | null
  windowMinutes: number | null
  extensionMinutes: number | null
}

export function parseTimes(values: RfqFormValues): ParsedTimes {
  const ms = (value: string) => {
    const parsed = parseLocalInput(value)
    return parsed.ok ? parsed.ms : null
  }
  return {
    start: ms(values.bidStartAt),
    close: ms(values.bidCloseAt),
    forced: ms(values.forcedCloseAt),
    windowMinutes: minutes(values.triggerWindowMinutes),
    extensionMinutes: minutes(values.extensionDurationMinutes),
  }
}

function timeError(value: string, emptyMessage: string): string | null {
  const parsed = parseLocalInput(value)
  if (parsed.ok) return null
  if (parsed.reason === 'empty') return emptyMessage
  if (parsed.reason === 'nonexistent') return 'That time doesn’t exist in your time zone (the clocks change then).'
  return 'Enter a valid date and time.'
}

export function validate(values: RfqFormValues, nowMs: number): FormErrors {
  const errors: FormErrors = {}

  const name = values.name.trim()
  if (!name) errors.name = 'Enter a name for the RFQ.'
  else if (name.length < 3) errors.name = 'Use at least 3 characters.'
  else if (name.length > 120) errors.name = 'Use at most 120 characters.'

  const reference = values.referenceId.trim().toUpperCase()
  if (reference && !REFERENCE_PATTERN.test(reference)) {
    errors.referenceId = 'Use 3–30 letters, digits or hyphens (e.g. RFQ-2026-0042).'
  }

  const { start, close, forced } = parseTimes(values)
  const startError = timeError(values.bidStartAt, 'Choose when bidding opens.')
  if (startError) errors.bidStartAt = startError
  else if (start !== null && start < nowMs - START_TOLERANCE_MS) errors.bidStartAt = 'Bid start can’t be in the past.'

  const closeError = timeError(values.bidCloseAt, 'Choose when bidding closes.')
  if (closeError) errors.bidCloseAt = closeError
  else if (start !== null && close !== null && close <= start) {
    errors.bidCloseAt = 'Bid close must be after the bid start.'
  }

  const forcedError = timeError(values.forcedCloseAt, 'Choose the forced close time.')
  if (forcedError) errors.forcedCloseAt = forcedError
  else if (close !== null && forced !== null && forced <= close) {
    errors.forcedCloseAt = 'Forced close must be after the bid close time.'
  }

  if (!values.pickupDate) errors.pickupDate = 'Choose the pickup or service date.'
  else if (!/^\d{4}-\d{2}-\d{2}$/.test(values.pickupDate)) errors.pickupDate = 'Enter a valid date.'
  else if (close !== null) {
    // The server compares with the close's UTC date; also require the local date, which is
    // what the buyer sees.
    const latest = [toLocalDate(close), toUtcDate(close)].sort().at(-1) as string
    if (values.pickupDate < latest) errors.pickupDate = 'Pickup / service date can’t be before the bid close date.'
  }

  if (minutes(values.triggerWindowMinutes) === null) {
    errors.triggerWindowMinutes = 'Enter whole minutes from 1 to 120.'
  }
  if (minutes(values.extensionDurationMinutes) === null) {
    errors.extensionDurationMinutes = 'Enter whole minutes from 1 to 120.'
  }
  return errors
}

/** The request body. Call only with values that passed `validate`. */
export function toPayload(values: RfqFormValues): RfqCreate {
  const { start, close, forced, windowMinutes, extensionMinutes } = parseTimes(values)
  if (start === null || close === null || forced === null || windowMinutes === null || extensionMinutes === null) {
    throw new Error('toPayload called with invalid values')
  }
  const reference = values.referenceId.trim().toUpperCase()
  return {
    name: values.name.trim(),
    reference_id: reference || null,
    pickup_date: values.pickupDate,
    bid_start_at: new Date(start).toISOString(),
    bid_close_at: new Date(close).toISOString(),
    forced_close_at: new Date(forced).toISOString(),
    auction_config: {
      trigger_window_minutes: windowMinutes,
      extension_duration_minutes: extensionMinutes,
      trigger_type: values.triggerType,
    },
  }
}

const SERVER_FIELDS: Record<string, FieldName> = {
  name: 'name',
  reference_id: 'referenceId',
  pickup_date: 'pickupDate',
  bid_start_at: 'bidStartAt',
  bid_close_at: 'bidCloseAt',
  forced_close_at: 'forcedCloseAt',
  'auction_config.trigger_window_minutes': 'triggerWindowMinutes',
  'auction_config.extension_duration_minutes': 'extensionDurationMinutes',
  'auction_config.trigger_type': 'triggerType',
}

/** Server error → messages next to fields, plus the first message that has no field. */
export function serverErrors(error: ApiError): { fields: FormErrors; other: string | null } {
  const fields: FormErrors = {}
  const unmatched: string[] = []
  for (const detail of error.details) {
    const field = detail.field ? SERVER_FIELDS[detail.field] : undefined
    if (field) fields[field] ??= detail.message
    else unmatched.push(detail.message)
  }
  return { fields, other: unmatched[0] ?? null }
}
