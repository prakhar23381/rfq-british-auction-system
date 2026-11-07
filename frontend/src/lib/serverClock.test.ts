import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { clockOffsetMs, recordServerTime, serverNow } from './serverClock'

const LOCAL = Date.UTC(2026, 10, 7, 12, 0, 0)
const iso = (ms: number) => new Date(ms).toISOString()

describe('server clock', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(LOCAL)
  })
  afterEach(() => vi.useRealTimers())

  it('defaults to the local clock', () => {
    expect(serverNow()).toBe(LOCAL)
  })

  it('applies the offset between server and local time', () => {
    recordServerTime(iso(LOCAL + 90_000))
    expect(clockOffsetMs()).toBe(90_000)
    expect(serverNow()).toBe(LOCAL + 90_000)
  })

  it('uses the median of the last five samples, so one slow response is ignored', () => {
    for (const offset of [1000, 1200, 30_000, 1100, 900]) recordServerTime(iso(LOCAL + offset))
    expect(clockOffsetMs()).toBe(1100)

    // Older samples age out.
    for (const offset of [-500, -500, -500]) recordServerTime(iso(LOCAL + offset))
    expect(clockOffsetMs()).toBe(-500)
  })

  it('averages the middle pair for an even number of samples', () => {
    recordServerTime(iso(LOCAL + 1000))
    recordServerTime(iso(LOCAL + 2000))
    expect(clockOffsetMs()).toBe(1500)
  })

  it('ignores missing or invalid times', () => {
    recordServerTime(undefined)
    recordServerTime(42)
    recordServerTime('yesterday')
    expect(clockOffsetMs()).toBe(0)
  })
})
