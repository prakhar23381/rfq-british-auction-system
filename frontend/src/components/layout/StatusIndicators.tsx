import { useQuery } from '@tanstack/react-query'
import { useEffect } from 'react'

import { api, queryKeys } from '../../api/endpoints'
import { useConnectionStatus } from '../../realtime/hooks'
import { getWsClient, type ConnectionStatus } from '../../realtime/wsClient'
import { Chip, type ChipTone } from '../ui/Chip'

const CONNECTION: Record<ConnectionStatus, { tone: ChipTone; label: string; title: string }> = {
  idle: { tone: 'plain', label: 'Offline', title: 'Live updates are off' },
  connecting: { tone: 'lilac', label: 'Connecting…', title: 'Connecting to live updates' },
  open: { tone: 'mint', label: 'Live', title: 'Live updates are on' },
  reconnecting: { tone: 'danger', label: 'Reconnecting…', title: 'Lost the live connection; retrying' },
}

/** Live-update connection state. Mounting it opens the shared WebSocket. */
export function ConnectionChip() {
  const status = useConnectionStatus()
  useEffect(() => getWsClient().start(), [])
  const { tone, label, title } = CONNECTION[status]
  return (
    <span role="status" title={title}>
      <Chip tone={tone} dot={status === 'open' ? 'pulse' : true}>
        {label}
      </Chip>
    </span>
  )
}

/** Backend health (database, Redis, live relay), polled every 30 s. */
export function SystemStatus() {
  const { data, isError } = useQuery({
    queryKey: queryKeys.health,
    queryFn: api.health,
    refetchInterval: 30_000,
    retry: false,
  })
  if (isError) {
    return <Chip tone="danger" dot>API unreachable</Chip>
  }
  if (!data) return <Chip dot>Checking systems…</Chip>
  const failing = (['db', 'redis', 'realtime'] as const).filter((key) => data[key] !== 'ok')
  return failing.length === 0 ? (
    <Chip tone="mint" dot="pulse">All systems normal</Chip>
  ) : (
    <Chip tone="danger" dot title={`Failing: ${failing.join(', ')}`}>
      Degraded: {failing.join(', ')}
    </Chip>
  )
}
