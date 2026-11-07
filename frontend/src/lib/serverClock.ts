/**
 * Server clock estimate. Every API response and WebSocket message carries `server_time`;
 * each one gives a sample of (server − local) clock offset. Countdowns use the median of the
 * last few samples, so a wrong device clock or one slow response can't shift them.
 */
import { parseInstant } from './time'

const MAX_SAMPLES = 5

let samples: number[] = []
let offsetMs = 0

export function recordServerTime(serverTime: unknown, receivedAt: number = Date.now()): void {
  if (typeof serverTime !== 'string') return
  const server = parseInstant(serverTime)
  if (Number.isNaN(server)) return
  samples = [...samples.slice(-(MAX_SAMPLES - 1)), server - receivedAt]
  offsetMs = median(samples)
}

/** Current server time in epoch milliseconds. */
export function serverNow(): number {
  return Date.now() + offsetMs
}

export function clockOffsetMs(): number {
  return offsetMs
}

export function resetServerClock(): void {
  samples = []
  offsetMs = 0
}

function median(values: number[]): number {
  const sorted = [...values].sort((a, b) => a - b)
  const mid = Math.floor(sorted.length / 2)
  return sorted.length % 2 === 1 ? sorted[mid] : (sorted[mid - 1] + sorted[mid]) / 2
}
