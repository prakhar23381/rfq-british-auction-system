import '@testing-library/jest-dom/vitest'
import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

import { setActingUserId } from '../api/client'
import { resetServerClock } from '../lib/serverClock'

/** jsdom's WebSocket would try a real connection; app tests use one that never opens. */
class IdleWebSocket {
  readyState = 0
  onopen: (() => void) | null = null
  onmessage: (() => void) | null = null
  onclose: (() => void) | null = null
  send(): void {}
  close(): void {
    this.readyState = 3
  }
}
globalThis.WebSocket = IdleWebSocket as unknown as typeof WebSocket

afterEach(() => {
  cleanup()
  window.localStorage.clear()
  setActingUserId(null)
  resetServerClock()
})
