import { describe, expect, it } from 'vitest'

import { formatCountdown, formatDate, formatDateTime, formatMoney, formatTime, initials } from './format'
import { parseInstant } from './time'

describe('formatMoney', () => {
  it('uses Indian digit grouping and hides zero paise', () => {
    expect(formatMoney('125000.00')).toBe('₹1,25,000')
    expect(formatMoney('10000000')).toBe('₹1,00,00,000')
    expect(formatMoney(999)).toBe('₹999')
  })

  it('shows paise when there are any', () => {
    expect(formatMoney('1234.5')).toBe('₹1,234.50')
    expect(formatMoney('0.05')).toBe('₹0.05')
  })

  it('handles other currencies and bad input', () => {
    expect(formatMoney('1500', 'USD')).toBe('$1,500')
    expect(formatMoney('abc')).toBe('—')
  })
})

describe('dates and times', () => {
  it('formats instants in the given time zone with its abbreviation', () => {
    const text = formatDateTime('2026-11-07T12:30:00Z', 'Asia/Kolkata')
    expect(text).toContain('7 Nov')
    expect(text).toContain('18:00')
    expect(text).toContain('IST')
    expect(formatTime('2026-11-07T12:30:05Z', 'UTC')).toBe('12:30')
    expect(formatTime('2026-11-07T12:30:05Z', 'UTC', true)).toBe('12:30:05')
  })

  it('formats calendar dates without shifting them across time zones', () => {
    expect(formatDate('2026-11-20')).toBe('20 Nov 2026')
    expect(formatDate('2026-01-01')).toBe('1 Jan 2026')
    expect(formatDate('20/11/2026')).toBe('—')
  })

  it('accepts the API’s microsecond timestamps', () => {
    expect(parseInstant('2026-11-07T12:35:00.123456Z')).toBe(Date.UTC(2026, 10, 7, 12, 35, 0, 123))
    expect(parseInstant('2026-11-07T12:35:00Z')).toBe(Date.UTC(2026, 10, 7, 12, 35))
    expect(formatDateTime('not a date')).toBe('—')
  })
})

describe('formatCountdown', () => {
  it.each([
    [0, '00:00'],
    [-5000, '00:00'],
    [1, '00:01'],
    [999, '00:01'],
    [1000, '00:01'],
    [1001, '00:02'],
    [59_000, '00:59'],
    [277_000, '04:37'],
    [3_600_000, '1:00:00'],
    [3_909_000, '1:05:09'],
    [86_400_000, '1d 00h'],
    [2 * 86_400_000 + 3 * 3_600_000 + 1, '2d 03h'],
    [Number.NaN, '00:00'],
  ])('%d ms → %s', (ms, label) => {
    expect(formatCountdown(ms)).toBe(label)
  })
})

describe('initials', () => {
  it('takes the first letters of the first two words', () => {
    expect(initials('Swift Cargo')).toBe('SC')
    expect(initials('BlueWave Logistics Ltd')).toBe('BL')
    expect(initials('acme')).toBe('AC')
    expect(initials('  ')).toBe('?')
  })
})
