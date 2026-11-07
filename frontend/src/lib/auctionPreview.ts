/** What a British auction's settings mean in practice, for the create form's live preview. */
import { MINUTE } from './datetimeLocal'

export interface ScheduleInput {
  startMs: number
  closeMs: number
  forcedMs: number
  windowMinutes: number
  extensionMinutes: number
}

export interface SchedulePreview {
  durationMinutes: number
  /** Start of the trigger window: close − X (never before the start). */
  windowStartMs: number
  windowCoversAuction: boolean
  /** Minutes between the bid close and the forced close. */
  roomMinutes: number
  /** ⌈(forced − close) / Y⌉: after this many the close sits at the forced close. */
  maxExtensions: number
  /** Length of the final extension, shorter than Y when it is cut at the forced close. */
  lastExtensionMinutes: number
}

/** `null` when the settings are inconsistent (the form shows field errors instead). */
export function previewSchedule(input: ScheduleInput): SchedulePreview | null {
  const { startMs, closeMs, forcedMs, windowMinutes: x, extensionMinutes: y } = input
  if (![startMs, closeMs, forcedMs, x, y].every(Number.isFinite)) return null
  if (closeMs <= startMs || forcedMs <= closeMs || x < 1 || y < 1) return null

  const roomMinutes = (forcedMs - closeMs) / MINUTE
  const maxExtensions = Math.ceil(roomMinutes / y)
  const windowStart = closeMs - x * MINUTE
  return {
    durationMinutes: (closeMs - startMs) / MINUTE,
    windowStartMs: Math.max(windowStart, startMs),
    windowCoversAuction: windowStart <= startMs,
    roomMinutes,
    maxExtensions,
    lastExtensionMinutes: roomMinutes - (maxExtensions - 1) * y,
  }
}

/** "45 min", "2 h", "1 h 30 min" */
export function formatMinutes(minutes: number): string {
  const whole = Math.round(minutes)
  const h = Math.floor(whole / 60)
  const m = whole % 60
  if (h === 0) return `${m} min`
  return m === 0 ? `${h} h` : `${h} h ${m} min`
}

/** A duration in seconds: "40 s", "5 min", "2 min 30 s", "1 h 5 min". */
export function formatDuration(totalSeconds: number): string {
  const seconds = Math.round(totalSeconds)
  if (seconds < 60) return `${seconds} s`
  const rest = seconds % 60
  const minutes = formatMinutes(Math.floor(seconds / 60))
  return rest && seconds < 3600 ? `${minutes} ${rest} s` : minutes
}
