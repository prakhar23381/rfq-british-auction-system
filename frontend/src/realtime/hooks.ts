import { useEffect, useRef, useSyncExternalStore } from 'react'

import type { ServerEvent } from './events'
import { type ConnectionStatus, getWsClient } from './wsClient'

export function useConnectionStatus(): ConnectionStatus {
  const client = getWsClient()
  return useSyncExternalStore(client.onStatusChange, client.getStatus)
}

/**
 * Receives live events for `channel` while mounted, and calls `onStale` when events may have
 * been missed (reconnect or server resync). The latest callbacks are always used.
 */
export function useChannel(
  channel: string | null,
  onEvent: (event: ServerEvent) => void,
  onStale?: () => void,
): void {
  const eventRef = useRef(onEvent)
  const staleRef = useRef(onStale)
  useEffect(() => {
    eventRef.current = onEvent
    staleRef.current = onStale
  })

  useEffect(() => {
    if (!channel) return
    const client = getWsClient()
    const unsubscribe = client.subscribe(channel, (event) => eventRef.current(event))
    const unlisten = client.onStale(() => staleRef.current?.())
    return () => {
      unsubscribe()
      unlisten()
    }
  }, [channel])
}
