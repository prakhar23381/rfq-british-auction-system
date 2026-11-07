import { describe, expect, it } from 'vitest'

import { formatMinutes, previewSchedule } from './auctionPreview'

const at = (h: number, m: number) => Date.UTC(2026, 10, 7, h, m)

describe('previewSchedule', () => {
  it('matches the assignment example: close 18:00, X=10, Y=5, forced 18:20', () => {
    const preview = previewSchedule({
      startMs: at(17, 0),
      closeMs: at(18, 0),
      forcedMs: at(18, 20),
      windowMinutes: 10,
      extensionMinutes: 5,
    })
    expect(preview).toEqual({
      durationMinutes: 60,
      windowStartMs: at(17, 50),
      windowCoversAuction: false,
      roomMinutes: 20,
      maxExtensions: 4,
      lastExtensionMinutes: 5,
    })
  })

  it('counts the shortened last extension: ⌈(forced − close) / Y⌉', () => {
    const preview = previewSchedule({
      startMs: at(17, 0),
      closeMs: at(18, 0),
      forcedMs: at(18, 22),
      windowMinutes: 10,
      extensionMinutes: 5,
    })
    expect(preview?.maxExtensions).toBe(5)
    expect(preview?.lastExtensionMinutes).toBe(2)

    const big = previewSchedule({ startMs: at(17, 0), closeMs: at(18, 0), forcedMs: at(18, 3), windowMinutes: 10, extensionMinutes: 30 })
    expect(big?.maxExtensions).toBe(1)
    expect(big?.lastExtensionMinutes).toBe(3)
  })

  it('caps the window at the start when X is longer than the auction', () => {
    const preview = previewSchedule({
      startMs: at(17, 55),
      closeMs: at(18, 0),
      forcedMs: at(18, 30),
      windowMinutes: 10,
      extensionMinutes: 5,
    })
    expect(preview?.windowStartMs).toBe(at(17, 55))
    expect(preview?.windowCoversAuction).toBe(true)
  })

  it('returns null for inconsistent settings', () => {
    const base = { startMs: at(17, 0), closeMs: at(18, 0), forcedMs: at(18, 30), windowMinutes: 10, extensionMinutes: 5 }
    expect(previewSchedule({ ...base, forcedMs: base.closeMs })).toBeNull()
    expect(previewSchedule({ ...base, closeMs: base.startMs })).toBeNull()
    expect(previewSchedule({ ...base, extensionMinutes: 0 })).toBeNull()
    expect(previewSchedule({ ...base, windowMinutes: Number.NaN })).toBeNull()
  })
})

describe('formatMinutes', () => {
  it.each([
    [5, '5 min'],
    [60, '1 h'],
    [90, '1 h 30 min'],
    [150, '2 h 30 min'],
  ])('%d → %s', (minutes, text) => expect(formatMinutes(minutes)).toBe(text))
})
