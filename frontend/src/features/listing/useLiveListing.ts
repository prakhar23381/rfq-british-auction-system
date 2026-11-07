/**
 * The auction listing over REST, kept live by the `listing` WebSocket channel.
 *
 * - Each event row is kept per RFQ and shown instead of the REST row while its `version` is
 *   newer, so a slow refetch can never move a row backwards.
 * - Events can change which rows belong on this page and their order (status, close time), so
 *   the list is also refetched shortly after (coalescing bursts of events).
 * - After a reconnect or a server resync, events may have been missed: refetch.
 */
import { keepPreviousData, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useMemo, useRef, useState } from 'react'

import { api, type ListParams, queryKeys } from '../../api/endpoints'
import type { RfqListItem } from '../../api/types'
import { LISTING_CHANNEL } from '../../realtime/events'
import { useChannel } from '../../realtime/hooks'

const REFETCH_DEBOUNCE_MS = 300
/** After a countdown hits zero, give the close/start job a moment, then ask the server. */
export const DUE_REFRESH_MS = 1500

export function useLiveListing(params: ListParams) {
  const queryClient = useQueryClient()
  const query = useQuery({
    queryKey: queryKeys.rfqList(params),
    queryFn: () => api.listRfqs(params),
    placeholderData: keepPreviousData,
  })

  const [live, setLive] = useState<ReadonlyMap<string, RfqListItem>>(() => new Map())
  const [updated, setUpdated] = useState<ReadonlySet<string>>(() => new Set())
  const timer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)

  const refreshSoon = useCallback(
    (delay = REFETCH_DEBOUNCE_MS) => {
      clearTimeout(timer.current)
      timer.current = setTimeout(
        () => void queryClient.invalidateQueries({ queryKey: queryKeys.rfqLists }),
        delay,
      )
    },
    [queryClient],
  )
  useEffect(() => () => clearTimeout(timer.current), [])

  useChannel(
    LISTING_CHANNEL,
    (event) => {
      if (event.type !== 'listing.updated' && event.type !== 'rfq.created') return
      const { item } = event.data
      setLive((current) => {
        const known = current.get(item.id)
        if (known && known.version >= item.version) return current
        return new Map(current).set(item.id, item)
      })
      setUpdated((current) => (current.has(item.id) ? current : new Set(current).add(item.id)))
      refreshSoon()
    },
    () => refreshSoon(0),
  )

  const items = useMemo(
    () =>
      (query.data?.items ?? []).map((item) => {
        const newer = live.get(item.id)
        return newer && newer.version > item.version ? newer : item
      }),
    [query.data, live],
  )

  const onDue = useCallback(() => refreshSoon(DUE_REFRESH_MS), [refreshSoon])

  return { query, items, updated, onDue }
}
