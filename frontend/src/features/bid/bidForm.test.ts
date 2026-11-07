import { describe, expect, it } from 'vitest'

import { ApiError } from '../../api/client'
import type { RankedBid } from '../../api/types'
import { centsToAmount, toCents } from '../../lib/money'
import { type BidFormValues, bidServerErrors, initialBidValues, toBidPayload, totalCents, validateBid } from './bidForm'

const PICKUP = '2026-11-20'

function values(overrides: Partial<BidFormValues> = {}): BidFormValues {
  return {
    carrierName: 'Swift Ocean Line',
    freight: '110000',
    origin: '8000',
    destination: '7000.50',
    transitDays: '24',
    validityDate: '2026-11-30',
    notes: '',
    ...overrides,
  }
}

const check = (v: BidFormValues, previousTotal: string | null = null) =>
  validateBid(v, { pickupDate: PICKUP, previousTotal })

describe('money', () => {
  it('works in paise without floating-point error', () => {
    expect(toCents('0.1')).toBe(10)
    expect(toCents('0.2')).toBe(20)
    expect((toCents('0.1') as number) + (toCents('0.2') as number)).toBe(30) // not 0.30000000000000004
    expect(toCents('12500.5')).toBe(1250050)
    expect(toCents(' 7 ')).toBe(700)
    for (const bad of ['', '-1', '1.234', '1,000', 'abc', '1e5', '.5']) expect(toCents(bad), bad).toBeNull()
    expect(centsToAmount(1250050)).toBe('12500.50')
    expect(centsToAmount(5)).toBe('0.05')
  })

  it('adds up the total', () => {
    expect(totalCents(values())).toBe(12_500_050)
    expect(totalCents(values({ origin: 'x' }))).toBeNull()
  })
})

describe('validateBid', () => {
  it('accepts a valid bid', () => expect(check(values())).toEqual({}))

  it.each<[string, Partial<BidFormValues>, string, string]>([
    ['missing carrier', { carrierName: ' ' }, 'carrierName', 'Enter the carrier or shipping line.'],
    ['short carrier', { carrierName: 'A' }, 'carrierName', 'Use at least 2 characters.'],
    ['missing freight', { freight: '' }, 'freight', 'Enter an amount (0 if none).'],
    ['three decimals', { origin: '1.234' }, 'origin', 'Enter an amount like 12500 or 12500.50.'],
    ['negative', { destination: '-5' }, 'destination', 'Enter an amount like 12500 or 12500.50.'],
    ['zero total', { freight: '0', origin: '0', destination: '0.00' }, 'total', 'The total must be more than zero.'],
    ['total too large', { freight: '999999999999.99', origin: '1' }, 'total', 'The total must be at most ₹9,99,99,99,99,999.99.'],
    ['zero transit', { transitDays: '0' }, 'transitDays', 'Enter whole days from 1 to 365.'],
    ['long transit', { transitDays: '366' }, 'transitDays', 'Enter whole days from 1 to 365.'],
    ['validity before pickup', { validityDate: '2026-11-19' }, 'validityDate', 'The quote must be valid on the pickup date or later.'],
    ['long notes', { notes: 'x'.repeat(501) }, 'notes', 'Use at most 500 characters.'],
  ])('%s', (_, overrides, field, message) => {
    expect(check(values(overrides))[field as keyof BidFormValues]).toBe(message)
  })

  it('requires a lower total than the supplier’s current bid', () => {
    expect(check(values(), '125000.50').total).toBe('Your new total must be lower than your current bid.')
    expect(check(values(), '125000.51').total).toBeUndefined()
  })
})

describe('initialBidValues', () => {
  it('starts from the supplier’s current bid', () => {
    const previous = {
      carrier_name: 'BlueWave Line',
      freight_charges: '112000.00',
      origin_charges: '6000.00',
      destination_charges: '3500.50',
      transit_time_days: 26,
      quote_validity_date: '2026-12-15',
    } as RankedBid
    expect(initialBidValues(previous, PICKUP)).toEqual({
      carrierName: 'BlueWave Line',
      freight: '112000',
      origin: '6000',
      destination: '3500.5',
      transitDays: '26',
      validityDate: '2026-12-15',
      notes: '',
    })
    expect(initialBidValues(undefined, PICKUP)).toMatchObject({ freight: '', origin: '0', validityDate: PICKUP })
  })
})

describe('toBidPayload', () => {
  it('sends money as two-decimal strings', () => {
    expect(toBidPayload(values({ notes: '  Includes BAF ' }))).toEqual({
      carrier_name: 'Swift Ocean Line',
      freight_charges: '110000.00',
      origin_charges: '8000.00',
      destination_charges: '7000.50',
      transit_time_days: 24,
      quote_validity_date: '2026-11-30',
      notes: 'Includes BAF',
    })
    expect(toBidPayload(values()).notes).toBeNull()
  })
})

describe('bidServerErrors', () => {
  it('maps fields and puts BID_NOT_LOWER on the total', () => {
    expect(
      bidServerErrors(
        new ApiError(422, 'VALIDATION_ERROR', 'Invalid', [{ field: 'quote_validity_date', message: 'Must be on or after pickup' }]),
      ),
    ).toEqual({ validityDate: 'Must be on or after pickup' })
    expect(bidServerErrors(new ApiError(422, 'BID_NOT_LOWER', 'Your bid must be lower than ₹1,21,500'))).toEqual({
      total: 'Your bid must be lower than ₹1,21,500',
    })
    expect(
      bidServerErrors(new ApiError(422, 'ZERO_TOTAL', 'x', [{ field: null, message: 'Total charges must be greater than zero' }])),
    ).toEqual({ total: 'Total charges must be greater than zero' })
  })
})
