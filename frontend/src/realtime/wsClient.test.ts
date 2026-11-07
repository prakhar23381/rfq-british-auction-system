import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { clockOffsetMs } from '../lib/serverClock'
import type { ServerEvent } from './events'
import { WsClient } from './wsClient'

class FakeSocket {
  readyState = 0
  sent: unknown[] = []
  onopen: (() => void) | null = null
  onmessage: ((event: { data: unknown }) => void) | null = null
  onclose: (() => void) | null = null

  send(data: string) {
    this.sent.push(JSON.parse(data))
  }
  close() {
    this.readyState = 3
    this.onclose?.()
  }
  // Test controls
  open() {
    this.readyState = 1
    this.onopen?.()
  }
  receive(message: object | string) {
    this.onmessage?.({ data: typeof message === 'string' ? message : JSON.stringify(message) })
  }
  drop() {
    this.readyState = 3
    this.onclose?.()
  }
}

let sockets: FakeSocket[]
const latest = () => sockets[sockets.length - 1]

function makeClient(overrides: Partial<ConstructorParameters<typeof WsClient>[0]> = {}) {
  return new WsClient({
    url: 'ws://test/ws',
    createSocket: () => {
      const socket = new FakeSocket()
      sockets.push(socket)
      return socket as unknown as WebSocket
    },
    random: () => 1, // no jitter: delays are exactly the backoff ceiling
    ...overrides,
  })
}

const event = (channel: string, version = 1): ServerEvent => ({
  type: 'listing.updated',
  channel,
  data: { version, item: {} as never },
  server_time: new Date().toISOString(),
})

describe('WsClient', () => {
  beforeEach(() => {
    sockets = []
    vi.useFakeTimers()
  })
  afterEach(() => vi.useRealTimers())

  it('subscribes once per channel when the socket opens, and routes events by channel', () => {
    const client = makeClient()
    const a = vi.fn()
    const b = vi.fn()
    const other = vi.fn()
    client.subscribe('listing', a)
    client.subscribe('listing', b)
    client.subscribe('rfq:1', other)
    expect(client.getStatus()).toBe('connecting')
    expect(sockets).toHaveLength(1)

    latest().open()
    expect(client.getStatus()).toBe('open')
    expect(latest().sent).toEqual([
      { action: 'subscribe', channel: 'listing' },
      { action: 'subscribe', channel: 'rfq:1' },
    ])

    latest().receive(event('listing'))
    expect(a).toHaveBeenCalledTimes(1)
    expect(b).toHaveBeenCalledTimes(1)
    expect(other).not.toHaveBeenCalled()
  })

  it('unsubscribes from the server only when the last handler leaves', () => {
    const client = makeClient()
    client.subscribe('rfq:1', vi.fn())
    latest().open()
    const off1 = client.subscribe('rfq:1', vi.fn())
    const off2 = client.subscribe('rfq:2', vi.fn())
    expect(latest().sent).toEqual([
      { action: 'subscribe', channel: 'rfq:1' },
      { action: 'subscribe', channel: 'rfq:2' },
    ])
    off1()
    off1() // twice is harmless
    expect(latest().sent).toHaveLength(2)
    off2()
    expect(latest().sent.at(-1)).toEqual({ action: 'unsubscribe', channel: 'rfq:2' })
    expect(client.channels).toEqual(['rfq:1'])
  })

  it('reconnects with growing delays, resubscribes, and reports the gap', () => {
    const client = makeClient()
    const stale = vi.fn()
    client.onStale(stale)
    client.subscribe('listing', vi.fn())
    latest().open()
    expect(stale).not.toHaveBeenCalled() // first connect is not a gap

    latest().drop()
    expect(client.getStatus()).toBe('reconnecting')
    vi.advanceTimersByTime(499)
    expect(sockets).toHaveLength(1)
    vi.advanceTimersByTime(1)
    expect(sockets).toHaveLength(2)

    latest().drop() // still down: next delay doubles
    vi.advanceTimersByTime(999)
    expect(sockets).toHaveLength(2)
    vi.advanceTimersByTime(1)
    expect(sockets).toHaveLength(3)

    latest().open()
    expect(client.getStatus()).toBe('open')
    expect(latest().sent).toEqual([{ action: 'subscribe', channel: 'listing' }])
    expect(stale).toHaveBeenCalledTimes(1)

    latest().drop() // a success resets the backoff
    vi.advanceTimersByTime(500)
    expect(sockets).toHaveLength(4)
  })

  it('caps the backoff and adds jitter', () => {
    const client = makeClient({ random: () => 0 })
    client.subscribe('listing', vi.fn())
    for (let i = 0; i < 10; i++) {
      latest().drop()
      vi.runOnlyPendingTimers()
    }
    // With random() = 0 the delay is half the ceiling: the 10 s cap gives 5 s.
    const before = sockets.length
    latest().drop()
    vi.advanceTimersByTime(4_999)
    expect(sockets).toHaveLength(before)
    vi.advanceTimersByTime(1)
    expect(sockets).toHaveLength(before + 1)
  })

  it('treats a server resync as a gap', () => {
    const client = makeClient()
    const stale = vi.fn()
    client.onStale(stale)
    client.subscribe('listing', vi.fn())
    latest().open()
    latest().receive({ type: 'resync', channel: null, data: {}, server_time: new Date().toISOString() })
    expect(stale).toHaveBeenCalledTimes(1)
  })

  it('keeps going when a handler throws or a message is malformed', () => {
    const errors = vi.spyOn(console, 'error').mockImplementation(() => {})
    const client = makeClient()
    const good = vi.fn()
    client.subscribe('listing', () => {
      throw new Error('bug in a handler')
    })
    client.subscribe('listing', good)
    latest().open()
    latest().receive('not json')
    latest().receive('[1,2]')
    latest().receive({ type: 'listing.updated' }) // no channel
    latest().receive(event('listing'))
    expect(good).toHaveBeenCalledTimes(1)
    expect(errors).toHaveBeenCalledTimes(1)
  })

  it('records server_time from every message', () => {
    const client = makeClient()
    client.subscribe('listing', vi.fn())
    latest().open()
    latest().receive({ type: 'pong', channel: null, data: {}, server_time: new Date(Date.now() + 5000).toISOString() })
    expect(clockOffsetMs()).toBe(5000)
  })

  it('pings to keep the connection alive', () => {
    const client = makeClient({ pingIntervalMs: 1000 })
    client.subscribe('listing', vi.fn())
    latest().open()
    vi.advanceTimersByTime(2000)
    expect(latest().sent.filter((m) => (m as { action: string }).action === 'ping')).toHaveLength(2)
  })

  it('stops cleanly without reconnecting', () => {
    const client = makeClient()
    client.subscribe('listing', vi.fn())
    latest().open()
    client.stop()
    expect(client.getStatus()).toBe('idle')
    vi.advanceTimersByTime(60_000)
    expect(sockets).toHaveLength(1)
    expect(vi.getTimerCount()).toBe(0)
  })

  it('notifies status listeners on changes only', () => {
    const client = makeClient()
    const listener = vi.fn()
    client.onStatusChange(listener)
    client.start()
    client.start() // already running
    latest().open()
    expect(listener).toHaveBeenCalledTimes(2) // connecting, open
  })
})
