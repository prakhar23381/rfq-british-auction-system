import { act, renderHook } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { recordServerTime } from '../lib/serverClock'
import { describeCountdown, useCountdown } from './useCountdown'

const T0 = Date.UTC(2026, 11, 1, 12, 0, 0)
const at = (ms: number) => new Date(T0 + ms).toISOString()

function advance(ms: number) {
  act(() => {
    vi.advanceTimersByTime(ms)
  })
}

describe('useCountdown', () => {
  beforeEach(() => {
    vi.useFakeTimers()
    vi.setSystemTime(T0)
  })
  afterEach(() => vi.useRealTimers())

  it('counts down once a second', () => {
    const { result } = renderHook(() => useCountdown(at(90_000)))
    expect(result.current.label).toBe('01:30')
    advance(1000)
    expect(result.current.label).toBe('01:29')
    advance(29_000)
    expect(result.current.label).toBe('01:00')
    expect(result.current.isFinalMinute).toBe(true)
  })

  it('lands on second boundaries even when started mid-second', () => {
    vi.setSystemTime(T0 + 400)
    const { result } = renderHook(() => useCountdown(at(10_000)))
    expect(result.current.label).toBe('00:10') // 9.6 s left rounds up
    advance(600)
    expect(result.current.label).toBe('00:09')
  })

  it('ticks four times a second in the last minute', () => {
    renderHook(() => useCountdown(at(5_000)))
    advance(0)
    expect(vi.getTimerCount()).toBe(1)
    const spy = vi.spyOn(globalThis, 'setTimeout')
    advance(1000)
    expect(spy).toHaveBeenCalledTimes(4)
  })

  it('stops at zero', () => {
    const { result } = renderHook(() => useCountdown(at(2_000)))
    advance(2_000)
    expect(result.current).toMatchObject({ label: '00:00', isOver: true, isFinalMinute: false })
    expect(vi.getTimerCount()).toBe(0)
  })

  it('is amber-worthy only inside the trigger window', () => {
    const { result } = renderHook(() => useCountdown(at(11 * 60_000), 10))
    expect(result.current.isInWindow).toBe(false)
    advance(60_000)
    expect(result.current.isInWindow).toBe(true)
  })

  it('follows the server clock, not the device clock', () => {
    recordServerTime(at(10 * 60_000)) // device is 10 minutes behind the server
    const { result } = renderHook(() => useCountdown(at(11 * 60_000)))
    expect(result.current.label).toBe('01:00')
  })

  it('restarts when the target moves (an extension)', () => {
    const { result, rerender } = renderHook(({ target }) => useCountdown(target), {
      initialProps: { target: at(3_000) },
    })
    advance(3_000)
    expect(result.current.isOver).toBe(true)
    rerender({ target: at(5 * 60_000 + 3_000) })
    advance(0)
    expect(result.current).toMatchObject({ isOver: false, label: '05:00' })
    advance(1000)
    expect(result.current.label).toBe('04:59')
  })

  it('handles a missing target', () => {
    const { result } = renderHook(() => useCountdown(null))
    expect(result.current.label).toBe('—')
    expect(result.current.isOver).toBe(false)
    expect(vi.getTimerCount()).toBe(0)
  })
})

describe('describeCountdown', () => {
  it('treats the exact close time as over', () => {
    expect(describeCountdown(0, 10)).toMatchObject({ isOver: true, isInWindow: false })
    expect(describeCountdown(1, 10)).toMatchObject({ isOver: false, isInWindow: true })
    expect(describeCountdown(10 * 60_000, 10).isInWindow).toBe(true)
    expect(describeCountdown(10 * 60_000 + 1, 10).isInWindow).toBe(false)
  })
})
