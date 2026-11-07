/**
 * Parses an API timestamp to epoch milliseconds (NaN if invalid).
 * The API can send microseconds (`…:00.123456Z`); only milliseconds are standard in JS.
 */
export function parseInstant(iso: string): number {
  return Date.parse(iso.replace(/(\.\d{3})\d+/, '$1'))
}
