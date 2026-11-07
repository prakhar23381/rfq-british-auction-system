/**
 * One WebSocket per tab, shared by every component.
 *
 * - `subscribe(channel, handler)` is reference counted: the server subscription is sent for
 *   the first handler on a channel and removed with the last one.
 * - Drops reconnect with exponential backoff and jitter; all channels are subscribed again.
 * - `onStale` fires after a reconnect and when the server sends `resync`: events may have been
 *   missed, so listeners refetch over REST.
 */
import { recordServerTime } from '../lib/serverClock'
import type { ClientMessage, ServerEvent } from './events'

export type ConnectionStatus = 'idle' | 'connecting' | 'open' | 'reconnecting'
export type EventHandler = (event: ServerEvent) => void

export interface WsClientOptions {
  url: string
  createSocket?: (url: string) => WebSocket
  minDelayMs?: number
  maxDelayMs?: number
  pingIntervalMs?: number
  random?: () => number
}

const OPEN = 1

export class WsClient {
  private readonly url: string
  private readonly createSocket: (url: string) => WebSocket
  private readonly minDelayMs: number
  private readonly maxDelayMs: number
  private readonly pingIntervalMs: number
  private readonly random: () => number

  private socket: WebSocket | null = null
  private readonly handlers = new Map<string, Set<EventHandler>>()
  private readonly staleListeners = new Set<() => void>()
  private readonly statusListeners = new Set<() => void>()
  private status: ConnectionStatus = 'idle'
  private running = false
  private hasConnected = false
  private attempts = 0
  private reconnectTimer: ReturnType<typeof setTimeout> | undefined
  private pingTimer: ReturnType<typeof setInterval> | undefined

  constructor(options: WsClientOptions) {
    this.url = options.url
    this.createSocket = options.createSocket ?? ((url) => new WebSocket(url))
    this.minDelayMs = options.minDelayMs ?? 500
    this.maxDelayMs = options.maxDelayMs ?? 10_000
    this.pingIntervalMs = options.pingIntervalMs ?? 25_000
    this.random = options.random ?? Math.random
  }

  /** Listen to a channel; returns the unsubscribe function. Starts the connection if needed. */
  subscribe(channel: string, handler: EventHandler): () => void {
    let set = this.handlers.get(channel)
    if (!set) {
      set = new Set()
      this.handlers.set(channel, set)
      this.send({ action: 'subscribe', channel })
    }
    set.add(handler)
    this.start()

    const handlers = set
    return () => {
      handlers.delete(handler)
      if (handlers.size === 0 && this.handlers.get(channel) === handlers) {
        this.handlers.delete(channel)
        this.send({ action: 'unsubscribe', channel })
      }
    }
  }

  /** Called when events may have been missed (reconnect, server `resync`). */
  onStale(listener: () => void): () => void {
    this.staleListeners.add(listener)
    return () => this.staleListeners.delete(listener)
  }

  onStatusChange = (listener: () => void): (() => void) => {
    this.statusListeners.add(listener)
    return () => this.statusListeners.delete(listener)
  }

  getStatus = (): ConnectionStatus => this.status

  get channels(): string[] {
    return [...this.handlers.keys()]
  }

  start(): void {
    if (this.running) return
    this.running = true
    this.connect()
  }

  stop(): void {
    this.running = false
    clearTimeout(this.reconnectTimer)
    this.stopPing()
    const socket = this.socket
    this.socket = null
    socket?.close()
    this.setStatus('idle')
  }

  private connect(): void {
    this.setStatus(this.hasConnected ? 'reconnecting' : 'connecting')
    let socket: WebSocket
    try {
      socket = this.createSocket(this.url)
    } catch {
      this.scheduleReconnect()
      return
    }
    this.socket = socket

    socket.onopen = () => {
      if (this.socket !== socket) return
      const isReconnect = this.hasConnected
      this.hasConnected = true
      this.attempts = 0
      for (const channel of this.handlers.keys()) this.send({ action: 'subscribe', channel })
      this.startPing()
      this.setStatus('open')
      if (isReconnect) this.emitStale()
    }
    socket.onmessage = (event: MessageEvent) => {
      if (this.socket === socket) this.handleMessage(event.data)
    }
    socket.onclose = () => {
      if (this.socket !== socket) return
      this.socket = null
      this.stopPing()
      if (this.running) this.scheduleReconnect()
    }
  }

  private scheduleReconnect(): void {
    this.setStatus(this.hasConnected ? 'reconnecting' : 'connecting')
    const ceiling = Math.min(this.maxDelayMs, this.minDelayMs * 2 ** this.attempts)
    this.attempts += 1
    const delay = ceiling / 2 + (this.random() * ceiling) / 2
    clearTimeout(this.reconnectTimer)
    this.reconnectTimer = setTimeout(() => {
      if (this.running) this.connect()
    }, delay)
  }

  private handleMessage(raw: unknown): void {
    if (typeof raw !== 'string') return
    let message: ServerEvent
    try {
      message = JSON.parse(raw) as ServerEvent
    } catch {
      return
    }
    if (typeof message !== 'object' || message === null || typeof message.type !== 'string') return
    recordServerTime(message.server_time)

    if (message.type === 'resync') {
      this.emitStale()
      return
    }
    if (message.type === 'error') {
      console.warn('WebSocket error from server:', message.data)
      return
    }
    if (!message.channel) return
    for (const handler of [...(this.handlers.get(message.channel) ?? [])]) {
      try {
        handler(message)
      } catch (error) {
        console.error('Live event handler failed', error)
      }
    }
  }

  private send(message: ClientMessage): void {
    // Not open yet: every channel is subscribed in `onopen`.
    if (this.socket?.readyState === OPEN) this.socket.send(JSON.stringify(message))
  }

  private startPing(): void {
    this.stopPing()
    this.pingTimer = setInterval(() => this.send({ action: 'ping' }), this.pingIntervalMs)
  }

  private stopPing(): void {
    clearInterval(this.pingTimer)
    this.pingTimer = undefined
  }

  private emitStale(): void {
    for (const listener of [...this.staleListeners]) listener()
  }

  private setStatus(status: ConnectionStatus): void {
    if (status === this.status) return
    this.status = status
    for (const listener of [...this.statusListeners]) listener()
  }
}

let shared: WsClient | null = null

export function defaultWsUrl(): string {
  const protocol = window.location.protocol === 'https:' ? 'wss:' : 'ws:'
  return `${protocol}//${window.location.host}/ws`
}

/** The tab's shared client. */
export function getWsClient(): WsClient {
  shared ??= new WsClient({ url: defaultWsUrl() })
  return shared
}
