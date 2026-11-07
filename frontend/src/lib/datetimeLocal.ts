/**
 * `<input type="datetime-local">` works in the browser's time zone with values like
 * "2026-11-07T18:30"; the API wants UTC instants. These helpers convert between the two.
 */

const pad = (n: number) => String(n).padStart(2, '0')

export const MINUTE = 60_000

/** Epoch ms → "YYYY-MM-DDTHH:mm" in the browser's time zone. */
export function toLocalInput(ms: number): string {
  const d = new Date(ms)
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}T${pad(d.getHours())}:${pad(d.getMinutes())}`
}

/** Epoch ms → "YYYY-MM-DD" (calendar date in the browser's time zone). */
export function toLocalDate(ms: number): string {
  const d = new Date(ms)
  return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())}`
}

/** Epoch ms → "YYYY-MM-DD" in UTC (how the server dates an instant). */
export function toUtcDate(ms: number): string {
  return new Date(ms).toISOString().slice(0, 10)
}

export type ParsedLocal =
  | { ok: true; ms: number }
  | { ok: false; reason: 'empty' | 'invalid' | 'nonexistent' }

/**
 * "YYYY-MM-DDTHH:mm[:ss]" in the browser's time zone → epoch ms. A wall-clock time skipped by
 * a daylight-saving change (e.g. 02:30 on a spring-forward night) is reported as `nonexistent`
 * rather than silently moved by an hour.
 */
export function parseLocalInput(value: string): ParsedLocal {
  if (!value) return { ok: false, reason: 'empty' }
  const match = /^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2})(?::(\d{2}))?$/.exec(value)
  if (!match) return { ok: false, reason: 'invalid' }
  const [y, mo, d, h, mi, s] = match.slice(1).map((part) => Number(part ?? 0))

  const calendar = new Date(Date.UTC(y, mo - 1, d, h, mi, s))
  const validCalendar =
    calendar.getUTCFullYear() === y &&
    calendar.getUTCMonth() === mo - 1 &&
    calendar.getUTCDate() === d &&
    calendar.getUTCHours() === h &&
    calendar.getUTCMinutes() === mi
  if (!validCalendar) return { ok: false, reason: 'invalid' }

  const local = new Date(y, mo - 1, d, h, mi, s, 0)
  if (local.getHours() !== h || local.getMinutes() !== mi || local.getDate() !== d) {
    return { ok: false, reason: 'nonexistent' }
  }
  return { ok: true, ms: local.getTime() }
}

/** Rounds up to the next whole minute. */
export function ceilToMinute(ms: number): number {
  return Math.ceil(ms / MINUTE) * MINUTE
}

/** The browser's time zone, e.g. { id: "Asia/Kolkata", abbreviation: "IST" }. */
export function localTimeZone(at: number = Date.now()): { id: string; abbreviation: string } {
  const id = Intl.DateTimeFormat().resolvedOptions().timeZone
  const abbreviation =
    new Intl.DateTimeFormat('en-IN', { timeZoneName: 'short' })
      .formatToParts(at)
      .find((part) => part.type === 'timeZoneName')?.value ?? id
  return { id, abbreviation }
}
