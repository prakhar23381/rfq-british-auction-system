import { describe, expect, it } from 'vitest'

import { ApiError } from '../../api/client'
import { withTimeZone } from '../../test/timeZone'
import { defaultValues, type RfqFormValues, serverErrors, shiftSchedule, toPayload, validate } from './form'

const NOW = Date.UTC(2026, 10, 7, 12, 0, 20) // 17:30:20 IST

function valid(overrides: Partial<RfqFormValues> = {}): RfqFormValues {
  return {
    name: 'Mumbai to Rotterdam',
    referenceId: '',
    pickupDate: '2026-11-20',
    bidStartAt: '2026-11-07T18:00',
    bidCloseAt: '2026-11-07T18:30',
    forcedCloseAt: '2026-11-07T19:00',
    triggerWindowMinutes: '10',
    extensionDurationMinutes: '5',
    triggerType: 'L1_CHANGE',
    ...overrides,
  }
}

const inIndia = <T>(fn: () => T) => withTimeZone('Asia/Kolkata', fn)

describe('defaultValues', () => {
  it('starts in 2 minutes (whole minute), closes 30 min later, forced 30 min after that', () =>
    inIndia(() => {
      const values = defaultValues(NOW)
      expect(values).toMatchObject({
        bidStartAt: '2026-11-07T17:33',
        bidCloseAt: '2026-11-07T18:03',
        forcedCloseAt: '2026-11-07T18:33',
        pickupDate: '2026-11-14',
        triggerWindowMinutes: '10',
        extensionDurationMinutes: '5',
        triggerType: 'L1_CHANGE',
      })
      // Only the name is left to fill in.
      expect(validate(values, NOW)).toEqual({ name: 'Enter a name for the RFQ.' })
    }))
})

describe('validate', () => {
  it('accepts a valid form', () => inIndia(() => expect(validate(valid(), NOW)).toEqual({})))

  it.each<[string, Partial<RfqFormValues>, keyof RfqFormValues, string]>([
    ['empty name', { name: '   ' }, 'name', 'Enter a name for the RFQ.'],
    ['short name', { name: 'ab' }, 'name', 'Use at least 3 characters.'],
    ['long name', { name: 'x'.repeat(121) }, 'name', 'Use at most 120 characters.'],
    ['bad reference', { referenceId: 'RFQ 1' }, 'referenceId', 'Use 3–30 letters, digits or hyphens (e.g. RFQ-2026-0042).'],
    ['short reference', { referenceId: 'ab' }, 'referenceId', 'Use 3–30 letters, digits or hyphens (e.g. RFQ-2026-0042).'],
    ['missing start', { bidStartAt: '' }, 'bidStartAt', 'Choose when bidding opens.'],
    ['start in the past', { bidStartAt: '2026-11-07T17:28' }, 'bidStartAt', 'Bid start can’t be in the past.'],
    ['close before start', { bidCloseAt: '2026-11-07T17:59' }, 'bidCloseAt', 'Bid close must be after the bid start.'],
    ['close equal to start', { bidCloseAt: '2026-11-07T18:00' }, 'bidCloseAt', 'Bid close must be after the bid start.'],
    ['forced equal to close', { forcedCloseAt: '2026-11-07T18:30' }, 'forcedCloseAt', 'Forced close must be after the bid close time.'],
    ['forced before close', { forcedCloseAt: '2026-11-07T18:10' }, 'forcedCloseAt', 'Forced close must be after the bid close time.'],
    ['missing forced', { forcedCloseAt: '' }, 'forcedCloseAt', 'Choose the forced close time.'],
    ['missing pickup', { pickupDate: '' }, 'pickupDate', 'Choose the pickup or service date.'],
    ['pickup before close', { pickupDate: '2026-11-06' }, 'pickupDate', 'Pickup / service date can’t be before the bid close date.'],
    ['X zero', { triggerWindowMinutes: '0' }, 'triggerWindowMinutes', 'Enter whole minutes from 1 to 120.'],
    ['X too big', { triggerWindowMinutes: '121' }, 'triggerWindowMinutes', 'Enter whole minutes from 1 to 120.'],
    ['X fraction', { triggerWindowMinutes: '2.5' }, 'triggerWindowMinutes', 'Enter whole minutes from 1 to 120.'],
    ['Y empty', { extensionDurationMinutes: '' }, 'extensionDurationMinutes', 'Enter whole minutes from 1 to 120.'],
  ])('%s', (_, overrides, field, message) =>
    inIndia(() => {
      const errors = validate(valid(overrides), NOW)
      expect(errors[field]).toBe(message)
    }),
  )

  it('allows a start up to a minute in the past, like the server', () =>
    inIndia(() => expect(validate(valid({ bidStartAt: '2026-11-07T17:30' }), NOW).bidStartAt).toBeUndefined()))

  it('requires the pickup on or after both the local and the UTC close date', () =>
    inIndia(() => {
      // Close at 01:30 IST on 21 Nov is still 20 Nov in UTC.
      const lateClose = valid({ bidCloseAt: '2026-11-21T01:30', forcedCloseAt: '2026-11-21T02:00', pickupDate: '2026-11-20' })
      expect(validate(lateClose, NOW).pickupDate).toBeDefined()
      expect(validate({ ...lateClose, pickupDate: '2026-11-21' }, NOW).pickupDate).toBeUndefined()
    }))

  it('catches a pickup the server would reject west of UTC', () =>
    withTimeZone('America/Los_Angeles', () => {
      // 19:00 PST on 20 Nov is already 21 Nov in UTC, which is the date the server checks.
      const evening = valid({ bidCloseAt: '2026-11-20T19:00', forcedCloseAt: '2026-11-20T19:30', pickupDate: '2026-11-20' })
      expect(validate(evening, NOW).pickupDate).toBe('Pickup / service date can’t be before the bid close date.')
      expect(validate({ ...evening, pickupDate: '2026-11-21' }, NOW).pickupDate).toBeUndefined()
    }))

  it('does not pile errors onto later fields when an earlier time is missing', () =>
    inIndia(() => {
      const errors = validate(valid({ bidStartAt: '' }), NOW)
      expect(errors.bidCloseAt).toBeUndefined()
    }))
})

describe('toPayload', () => {
  it('sends UTC instants, the trimmed name and an upper-case reference', () =>
    inIndia(() =>
      expect(toPayload(valid({ name: '  Mumbai to Rotterdam ', referenceId: ' rfq-2026-0042 ' }))).toEqual({
        name: 'Mumbai to Rotterdam',
        reference_id: 'RFQ-2026-0042',
        pickup_date: '2026-11-20',
        bid_start_at: '2026-11-07T12:30:00.000Z',
        bid_close_at: '2026-11-07T13:00:00.000Z',
        forced_close_at: '2026-11-07T13:30:00.000Z',
        auction_config: { trigger_window_minutes: 10, extension_duration_minutes: 5, trigger_type: 'L1_CHANGE' },
      }),
    ))

  it('omits a blank reference so the server generates one', () =>
    inIndia(() => expect(toPayload(valid()).reference_id).toBeNull()))

  it('refuses invalid values', () => expect(() => toPayload(valid({ bidStartAt: '' }))).toThrow())
})

describe('shiftSchedule', () => {
  it('moves the schedule and keeps its durations', () =>
    inIndia(() => {
      const shifted = shiftSchedule(valid({ bidCloseAt: '2026-11-07T18:45' }), Date.UTC(2026, 10, 7, 13, 0)) // 18:30 IST
      expect(shifted).toMatchObject({
        bidStartAt: '2026-11-07T18:30',
        bidCloseAt: '2026-11-07T19:15',
        forcedCloseAt: '2026-11-07T19:30',
      })
    }))
})

describe('serverErrors', () => {
  it('puts server messages next to the right fields', () => {
    const error = new ApiError(422, 'FORCED_CLOSE_NOT_AFTER_CLOSE', 'Forced bid close time must be later', [
      { field: 'forced_close_at', message: 'Forced bid close time must be later than the bid close time' },
      { field: 'auction_config.trigger_window_minutes', message: 'Input should be less than or equal to 120' },
    ])
    expect(serverErrors(error)).toEqual({
      fields: {
        forcedCloseAt: 'Forced bid close time must be later than the bid close time',
        triggerWindowMinutes: 'Input should be less than or equal to 120',
      },
      other: null,
    })
  })

  it('keeps messages without a known field for the banner', () => {
    const duplicate = new ApiError(409, 'DUPLICATE_REFERENCE', 'Reference ID X is already in use', [
      { field: 'reference_id', message: 'Already in use' },
    ])
    expect(serverErrors(duplicate).fields).toEqual({ referenceId: 'Already in use' })

    const odd = new ApiError(422, 'VALIDATION_ERROR', 'Invalid request', [{ field: 'surprise', message: 'Huh' }])
    expect(serverErrors(odd)).toEqual({ fields: {}, other: 'Huh' })
  })
})
