import '@testing-library/jest-dom/vitest'

import { cleanup } from '@testing-library/react'
import { afterEach } from 'vitest'

import { setActingUserId } from '../api/client'
import { resetServerClock } from '../lib/serverClock'
import { resetWsClient } from '../realtime/wsClient'
import { FakeWebSocket } from './fakeWebSocket'

// jsdom's WebSocket would try a real connection. The fake stays "connecting" unless a test
// opens it (see fakeWebSocket.ts).
globalThis.WebSocket = FakeWebSocket as unknown as typeof WebSocket

afterEach(() => {
  cleanup()
  resetWsClient()
  FakeWebSocket.instances = []
  window.localStorage.clear()
  setActingUserId(null)
  resetServerClock()
})
