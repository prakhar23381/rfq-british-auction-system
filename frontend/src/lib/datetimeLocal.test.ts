import { describe, expect, it } from 'vitest'

import { withTimeZone } from '../test/timeZone'
import { ceilToMinute, localTimeZone, parseLocalInput, toLocalDate, toLocalInput, toUtcDate } from './datetimeLocal'

describe('datetime-local ↔ UTC', () => {
  it('converts both ways in India (UTC+5:30)', () =>
    withTimeZone('Asia/Kolkata', () => {
      const instant = Date.UTC(2026, 10, 7, 12, 30) // 18:00 IST
      expect(toLocalInput(instant)).toBe('2026-11-07T18:00')
      expect(parseLocalInput('2026-11-07T18:00')).toEqual({ ok: true, ms: instant })
      expect(new Date(instant).toISOString()).toBe('2026-11-07T12:30:00.000Z')
      const zone = localTimeZone(instant)
      expect(zone.abbreviation).toBe('IST')
      expect(zone.id).toMatch(/^Asia\/(Kolkata|Calcutta)$/) // ICU may report the old alias
    }))

  it('converts both ways west of UTC', () =>
    withTimeZone('America/Los_Angeles', () => {
      const instant = Date.UTC(2026, 10, 8, 3, 15) // 19:15 PST on 7 Nov
      expect(toLocalInput(instant)).toBe('2026-11-07T19:15')
      expect(parseLocalInput('2026-11-07T19:15')).toEqual({ ok: true, ms: instant })
    }))

  it('tells the local calendar date from the UTC one', () =>
    withTimeZone('Asia/Kolkata', () => {
      const lateEvening = Date.UTC(2026, 10, 7, 20, 0) // 01:30 IST on 8 Nov
      expect(toLocalDate(lateEvening)).toBe('2026-11-08')
      expect(toUtcDate(lateEvening)).toBe('2026-11-07')
    }))

  it('reports wall-clock times skipped by daylight saving instead of moving them', () =>
    withTimeZone('America/New_York', () => {
      expect(parseLocalInput('2026-03-08T02:30')).toEqual({ ok: false, reason: 'nonexistent' })
      // 01:30 happens twice when clocks go back; the first one (EDT) is used.
      expect(parseLocalInput('2026-11-01T01:30')).toEqual({ ok: true, ms: Date.UTC(2026, 10, 1, 5, 30) })
      // Round trip across the change.
      const afterChange = Date.UTC(2026, 2, 8, 7, 0) // 03:00 EDT
      expect(toLocalInput(afterChange)).toBe('2026-03-08T03:00')
    }))

  it('rejects empty and malformed values', () => {
    expect(parseLocalInput('')).toEqual({ ok: false, reason: 'empty' })
    expect(parseLocalInput('tomorrow')).toEqual({ ok: false, reason: 'invalid' })
    expect(parseLocalInput('2026-02-30T10:00')).toEqual({ ok: false, reason: 'invalid' })
    expect(parseLocalInput('2026-11-07T24:00')).toEqual({ ok: false, reason: 'invalid' })
    expect(parseLocalInput('2026-11-07T18:00:30').ok).toBe(true) // seconds are allowed
  })

  it('rounds up to the next minute', () => {
    expect(ceilToMinute(Date.UTC(2026, 0, 1, 10, 0, 0))).toBe(Date.UTC(2026, 0, 1, 10, 0))
    expect(ceilToMinute(Date.UTC(2026, 0, 1, 10, 0, 1))).toBe(Date.UTC(2026, 0, 1, 10, 1))
  })
})
