/**
 * Fetch wrapper for the REST API: sends the acting user (`X-User-Id`), records `server_time`
 * for the server clock, and turns the error envelope into a typed `ApiError`.
 */
import { recordServerTime } from '../lib/serverClock'
import type { ErrorDetail } from './types'

export class ApiError extends Error {
  readonly status: number
  readonly code: string
  readonly details: ErrorDetail[]

  constructor(status: number, code: string, message: string, details: ErrorDetail[] = []) {
    super(message)
    this.name = 'ApiError'
    this.status = status
    this.code = code
    this.details = details
  }

  /** Field name → message, for showing server validation errors next to form inputs. */
  fieldErrors(): Record<string, string> {
    const errors: Record<string, string> = {}
    for (const detail of this.details) {
      if (detail.field && !(detail.field in errors)) errors[detail.field] = detail.message
    }
    return errors
  }
}

let actingUserId: string | null = null

/** Set by the user context whenever the "acting as" user changes. */
export function setActingUserId(id: string | null): void {
  actingUserId = id
}

export type QueryParams = Record<string, string | number | boolean | null | undefined>

export interface RequestOptions {
  method?: 'GET' | 'POST'
  body?: unknown
  query?: QueryParams
  signal?: AbortSignal
}

export function buildUrl(path: string, query?: QueryParams): string {
  const params = new URLSearchParams()
  for (const [key, value] of Object.entries(query ?? {})) {
    if (value !== undefined && value !== null && value !== '') params.set(key, String(value))
  }
  const search = params.toString()
  return search ? `${path}?${search}` : path
}

export async function request<T>(path: string, options: RequestOptions = {}): Promise<T> {
  const headers: Record<string, string> = { Accept: 'application/json' }
  if (options.body !== undefined) headers['Content-Type'] = 'application/json'
  if (actingUserId) headers['X-User-Id'] = actingUserId

  let response: Response
  try {
    response = await fetch(buildUrl(path, options.query), {
      method: options.method ?? 'GET',
      headers,
      body: options.body === undefined ? undefined : JSON.stringify(options.body),
      signal: options.signal,
    })
  } catch (error) {
    if (error instanceof DOMException && error.name === 'AbortError') throw error
    throw new ApiError(0, 'NETWORK_ERROR', 'Could not reach the server.')
  }

  const payload: unknown = await response.json().catch(() => null)
  if (isRecord(payload)) recordServerTime(payload.server_time)

  if (!response.ok) {
    const error = isRecord(payload) && isRecord(payload.error) ? payload.error : null
    throw new ApiError(
      response.status,
      typeof error?.code === 'string' ? error.code : `HTTP_${response.status}`,
      typeof error?.message === 'string' ? error.message : `Request failed (${response.status})`,
      Array.isArray(error?.details) ? (error.details as ErrorDetail[]) : [],
    )
  }
  return payload as T
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value)
}
