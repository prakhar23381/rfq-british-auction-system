// Tests run in Node; the app's tsconfig has browser types only.
declare const process: { env: Record<string, string | undefined> }

/** Runs `fn` with the process in another time zone (Node re-reads TZ when it changes). */
export function withTimeZone<T>(timeZone: string, fn: () => T): T {
  const previous = process.env.TZ
  process.env.TZ = timeZone
  try {
    return fn()
  } finally {
    if (previous === undefined) delete process.env.TZ
    else process.env.TZ = previous
  }
}

/** Switches the process time zone until the returned function is called. */
export function setTimeZone(timeZone: string): () => void {
  const previous = process.env.TZ
  process.env.TZ = timeZone
  return () => {
    if (previous === undefined) delete process.env.TZ
    else process.env.TZ = previous
  }
}
