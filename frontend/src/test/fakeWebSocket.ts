import { act } from '@testing-library/react'

/** Stand-in for the browser WebSocket in tests: records what is sent, lets tests push messages. */
export class FakeWebSocket {
  static instances: FakeWebSocket[] = []

  readyState = 0
  sent: unknown[] = []
  onopen: (() => void) | null = null
  onmessage: ((event: { data: unknown }) => void) | null = null
  onclose: (() => void) | null = null

  constructor() {
    FakeWebSocket.instances.push(this)
  }

  send(data: string): void {
    this.sent.push(JSON.parse(data))
  }

  close(): void {
    this.readyState = 3
    this.onclose?.()
  }
}

/** Opens the app's current socket (as if the server accepted it). */
export function openSocket(): FakeWebSocket {
  const socket = FakeWebSocket.instances.at(-1)
  if (!socket) throw new Error('No WebSocket was created')
  act(() => {
    socket.readyState = 1
    socket.onopen?.()
  })
  return socket
}

/** Delivers a server message to the app's current socket. */
export function serverSends(message: object): void {
  const socket = FakeWebSocket.instances.at(-1)
  if (!socket) throw new Error('No WebSocket was created')
  act(() => {
    socket.onmessage?.({ data: JSON.stringify({ server_time: new Date().toISOString(), ...message }) })
  })
}
