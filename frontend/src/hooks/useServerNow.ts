import { useEffect, useState } from 'react'

import { serverNow } from '../lib/serverClock'

/** Server time, refreshed every `intervalMs` (pass null to stop ticking). */
export function useServerNow(intervalMs: number | null = 1000): number {
  const [now, setNow] = useState(serverNow)
  useEffect(() => {
    if (intervalMs === null) return
    const timer = setInterval(() => setNow(serverNow()), intervalMs)
    return () => clearInterval(timer)
  }, [intervalMs])
  return now
}
