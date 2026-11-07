import type { AuctionStatus, TriggerType } from '../api/types'
import { parseInstant } from './time'

const moneyFormats = new Map<string, Intl.NumberFormat>()

/** ₹1,25,000 (Indian grouping); paise are shown only when there are any. */
export function formatMoney(amount: string | number, currency = 'INR'): string {
  const value = typeof amount === 'number' ? amount : Number(amount)
  if (!Number.isFinite(value)) return '—'
  const digits = Number.isInteger(value) ? 0 : 2
  const key = `${currency}:${digits}`
  let format = moneyFormats.get(key)
  if (!format) {
    format = new Intl.NumberFormat('en-IN', {
      style: 'currency',
      currency,
      minimumFractionDigits: digits,
      maximumFractionDigits: digits,
    })
    moneyFormats.set(key, format)
  }
  return format.format(value)
}

/** "7 Nov, 18:05 IST" in the browser's time zone (or `timeZone`). */
export function formatDateTime(iso: string, timeZone?: string): string {
  const ms = parseInstant(iso)
  if (Number.isNaN(ms)) return '—'
  return new Intl.DateTimeFormat('en-IN', {
    day: 'numeric',
    month: 'short',
    hour: '2-digit',
    minute: '2-digit',
    hourCycle: 'h23',
    timeZoneName: 'short',
    timeZone,
  }).format(ms)
}

/** "18:05:30" in the browser's time zone (or `timeZone`). */
export function formatTime(iso: string, timeZone?: string, seconds = false): string {
  const ms = parseInstant(iso)
  if (Number.isNaN(ms)) return '—'
  return new Intl.DateTimeFormat('en-IN', {
    hour: '2-digit',
    minute: '2-digit',
    second: seconds ? '2-digit' : undefined,
    hourCycle: 'h23',
    timeZone,
  }).format(ms)
}

/** A calendar date (`YYYY-MM-DD`, no time zone) as "20 Nov 2026". */
export function formatDate(date: string): string {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(date)
  if (!match) return '—'
  const [, y, m, d] = match
  return new Intl.DateTimeFormat('en-IN', {
    day: 'numeric',
    month: 'short',
    year: 'numeric',
    timeZone: 'UTC',
  }).format(Date.UTC(Number(y), Number(m) - 1, Number(d)))
}

/** A countdown label: "2d 03h", "1:05:09", "04:37", "00:00". Rounds up to the next second. */
export function formatCountdown(ms: number): string {
  if (!Number.isFinite(ms) || ms <= 0) return '00:00'
  const total = Math.ceil(ms / 1000)
  const days = Math.floor(total / 86_400)
  const hours = Math.floor((total % 86_400) / 3600)
  const minutes = Math.floor((total % 3600) / 60)
  const seconds = total % 60
  const pad = (n: number) => String(n).padStart(2, '0')
  if (days > 0) return `${days}d ${pad(hours)}h`
  if (hours > 0) return `${hours}:${pad(minutes)}:${pad(seconds)}`
  return `${pad(minutes)}:${pad(seconds)}`
}

export const STATUS_LABELS: Record<AuctionStatus, string> = {
  SCHEDULED: 'Upcoming',
  ACTIVE: 'Active',
  CLOSED: 'Closed',
  FORCE_CLOSED: 'Force closed',
}

export const TRIGGER_LABELS: Record<TriggerType, string> = {
  BID_RECEIVED: 'Any bid received',
  ANY_RANK_CHANGE: 'Any supplier rank change',
  L1_CHANGE: 'Lowest bidder (L1) changes',
}

export function initials(name: string): string {
  const words = name.trim().split(/\s+/).filter(Boolean)
  const letters = words.length > 1 ? words[0][0] + words[1][0] : (words[0] ?? '?').slice(0, 2)
  return letters.toUpperCase()
}
