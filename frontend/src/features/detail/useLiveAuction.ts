/**
 * One auction's details and activity log over REST, kept live by its `rfq:{id}` channel.
 *
 * - Events patch the cached detail only when their `version` is at least the cached one, and
 *   a REST response never replaces a newer cached snapshot (late responses are ignored).
 * - Activity entries from events are merged into the first page (each entry arrives once).
 * - After a reconnect or resync, everything is refetched.
 */
import { type InfiniteData, useInfiniteQuery, useQuery, useQueryClient } from '@tanstack/react-query'
import { useCallback, useEffect, useRef, useState } from 'react'

import { api, queryKeys } from '../../api/endpoints'
import type { Activity, ActivityList, RfqDetail } from '../../api/types'
import { useToast } from '../../components/ui/toastContext'
import { formatTime } from '../../lib/format'
import { rfqChannel, type ServerEvent } from '../../realtime/events'
import { useChannel } from '../../realtime/hooks'
import { useActingUser } from '../../user/userContext'

export const DUE_REFRESH_MS = 1500

function mergeNewest(entries: Activity[], page: ActivityList): ActivityList {
  const known = new Set(page.items.map((item) => item.id))
  const fresh = entries.filter((entry) => !known.has(entry.id))
  if (fresh.length === 0) return page
  return { ...page, items: [...fresh, ...page.items].sort((a, b) => b.id - a.id) }
}

export function useLiveAuction(id: string) {
  const queryClient = useQueryClient()
  const toast = useToast()
  const { user } = useActingUser()
  const detailKey = queryKeys.rfq(id)
  const activityKey = queryKeys.activity(id)

  const detail = useQuery({
    queryKey: detailKey,
    queryFn: async () => {
      const fresh = await api.getRfq(id)
      const cached = queryClient.getQueryData<RfqDetail>(detailKey)
      // A live event may have landed while this request was in flight.
      return cached && cached.rfq.version > fresh.rfq.version ? cached : fresh
    },
  })

  const activity = useInfiniteQuery({
    queryKey: activityKey,
    queryFn: async ({ pageParam }) => {
      const page = await api.activity(id, pageParam)
      if (pageParam !== undefined) return page
      const cached = queryClient.getQueryData<InfiniteData<ActivityList>>(activityKey)?.pages[0]
      const newest = page.items[0]?.id ?? 0
      return cached ? mergeNewest(cached.items.filter((item) => item.id > newest), page) : page
    },
    initialPageParam: undefined as number | undefined,
    getNextPageParam: (last) => last.next_before_id ?? undefined,
  })

  /** Suppliers whose ranking rows changed in the last event (rows flash). */
  const [changedSuppliers, setChangedSuppliers] = useState<ReadonlySet<string>>(() => new Set())
  /** Version of the last change caused by the acting user's own bid (they already got a toast). */
  const ownChange = useRef(0)
  /** Bumped on every extension, so the header can replay its pulse. */
  const [extensionPulse, setExtensionPulse] = useState(0)

  const patchDetail = useCallback(
    (version: number, patch: (current: RfqDetail) => RfqDetail) =>
      queryClient.setQueryData<RfqDetail>(detailKey, (current) =>
        current && version >= current.rfq.version ? patch(current) : current,
      ),
    // detailKey is derived from id
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [queryClient, id],
  )

  const addActivity = useCallback(
    (entries: Activity[]) =>
      queryClient.setQueryData<InfiniteData<ActivityList>>(activityKey, (data) => {
        if (!data || entries.length === 0) return data
        const [first, ...rest] = data.pages
        return { ...data, pages: [mergeNewest(entries, first), ...rest] }
      }),
    // eslint-disable-next-line react-hooks/exhaustive-deps
    [queryClient, id],
  )

  const refreshAll = useCallback(() => {
    void queryClient.invalidateQueries({ queryKey: queryKeys.rfq(id) })
    void queryClient.invalidateQueries({ queryKey: queryKeys.activity(id) })
    void queryClient.invalidateQueries({ queryKey: queryKeys.bidHistory(id) })
  }, [queryClient, id])

  const onEvent = (event: ServerEvent) => {
    switch (event.type) {
      case 'bid.submitted': {
        const data = event.data
        const before = queryClient.getQueryData<RfqDetail>(detailKey)
        if (before && data.version < before.rfq.version) return
        const oldRanks = new Map(before?.ranking.map((row) => [row.supplier.id, row.rank]) ?? [])
        const changed = new Set(
          data.ranking.filter((row) => oldRanks.get(row.supplier.id) !== row.rank).map((row) => row.supplier.id),
        )
        changed.add(data.bid.supplier.id)
        if (data.bid.supplier.id === user?.id) ownChange.current = data.version
        setChangedSuppliers(changed)

        patchDetail(data.version, (current) => ({ ...current, rfq: data.rfq, ranking: data.ranking, stats: data.stats }))
        addActivity(data.activity)
        void queryClient.invalidateQueries({ queryKey: queryKeys.bidHistory(id) })

        // Tell a supplier when someone else's bid pushed them down.
        if (user?.role === 'SUPPLIER' && data.bid.supplier.id !== user.id) {
          const mine = data.ranking.find((row) => row.supplier.id === user.id)
          const previous = oldRanks.get(user.id)
          if (mine && previous !== undefined && mine.rank > previous) {
            toast.show({
              tone: 'error',
              title: `You’ve been outbid · now ${mine.rank_label}`,
              description: `${data.bid.supplier.company_name} bid lower.`,
            })
          }
        }
        break
      }
      case 'auction.extended': {
        const data = event.data
        patchDetail(data.version, (current) => ({
          ...current,
          rfq: { ...current.rfq, current_close_at: data.new_close_at, extension_count: data.extension_count },
        }))
        addActivity(data.activity)
        setExtensionPulse((n) => n + 1)
        if (data.version === ownChange.current) break // the bid form already said so
        toast.show({
          tone: 'time',
          title: `Auction extended to ${formatTime(data.new_close_at)}`,
          description: data.capped ? `${data.reason} (capped at the forced close)` : data.reason,
        })
        break
      }
      case 'auction.status': {
        const data = event.data
        patchDetail(data.version, (current) => ({ ...current, rfq: data.rfq }))
        addActivity(data.activity)
        const titles = { ACTIVE: 'Bidding is open', CLOSED: 'Auction closed', FORCE_CLOSED: 'Auction force closed' }
        if (data.status in titles) {
          toast.show({ tone: data.status === 'ACTIVE' ? 'success' : 'info', title: titles[data.status as keyof typeof titles] })
        }
        break
      }
    }
  }

  useChannel(rfqChannel(id), onEvent, refreshAll)

  // Countdown hit zero: if no status event arrives, ask the server (status is derived there).
  const dueTimer = useRef<ReturnType<typeof setTimeout> | undefined>(undefined)
  const onDue = useCallback(() => {
    clearTimeout(dueTimer.current)
    dueTimer.current = setTimeout(refreshAll, DUE_REFRESH_MS)
  }, [refreshAll])
  useEffect(() => () => clearTimeout(dueTimer.current), [])

  return { detail, activity, changedSuppliers, extensionPulse, onDue, refreshAll }
}
