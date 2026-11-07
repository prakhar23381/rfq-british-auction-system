import { useEffect, useState } from 'react'

import { formatCountdown } from '../lib/format'
import { serverNow } from '../lib/serverClock'
import { parseInstant } from '../lib/time'

export interface Countdown {
  /** Milliseconds left (negative once passed); NaN without a target. */
  ms: number
  label: string
  isOver: boolean
  /** Inside the last minute: the label ticks every 250 ms. */
  isFinalMinute: boolean
  /** Inside the British auction trigger window (last X minutes before close). */
  isInWindow: boolean
}

const SECOND = 1000
const FAST = 250

export function describeCountdown(ms: number, windowMinutes?: number): Countdown {
  const valid = Number.isFinite(ms)
  const isOver = valid && ms <= 0
  return {
    ms,
    label: valid ? formatCountdown(ms) : '—',
    isOver,
    isFinalMinute: valid && !isOver && ms <= 60 * SECOND,
    isInWindow:
      valid && !isOver && windowMinutes !== undefined && ms <= windowMinutes * 60 * SECOND,
  }
}

/**
 * Time left until `target` on the server's clock. Ticks once a second, four times a second in
 * the last minute, and stops at zero. Ticks land on second boundaries so the label never skips.
 */
export function useCountdown(target: string | null | undefined, windowMinutes?: number): Countdown {
  const targetMs = target ? parseInstant(target) : Number.NaN
  const [now, setNow] = useState(serverNow)

  useEffect(() => {
    if (Number.isNaN(targetMs)) return
    let timer: ReturnType<typeof setTimeout> | undefined

    const schedule = () => {
      const left = targetMs - serverNow()
      if (left <= 0) return
      const interval = left <= 60 * SECOND ? FAST : SECOND
      const delay = left % interval || interval
      timer = setTimeout(() => {
        setNow(serverNow())
        schedule()
      }, delay)
    }

    // Re-read the clock straight away when the target changes (e.g. an extension).
    timer = setTimeout(() => {
      setNow(serverNow())
      schedule()
    }, 0)
    return () => clearTimeout(timer)
  }, [targetMs])

  return describeCountdown(targetMs - now, windowMinutes)
}
