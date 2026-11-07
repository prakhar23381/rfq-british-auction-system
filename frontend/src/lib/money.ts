/** Money as integer paise, so totals never suffer floating-point error. */

const AMOUNT = /^(\d{1,12})(?:\.(\d{1,2}))?$/

/** "12500.5" → 1250050; null when not a valid non-negative amount with ≤ 2 decimals. */
export function toCents(value: string): number | null {
  const match = AMOUNT.exec(value.trim())
  if (!match) return null
  const [, whole, fraction = ''] = match
  return Number(whole) * 100 + Number(fraction.padEnd(2, '0'))
}

/** 1250050 → "12500.50" (the API's money format). */
export function centsToAmount(cents: number): string {
  const whole = Math.floor(cents / 100)
  return `${whole}.${String(cents % 100).padStart(2, '0')}`
}
