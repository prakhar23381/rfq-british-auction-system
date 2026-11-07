import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

import { clockOffsetMs } from '../lib/serverClock'
import { ApiError, buildUrl, request, setActingUserId } from './client'
import { errorMessage } from './errors'

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), { status, headers: { 'Content-Type': 'application/json' } })
}

const fetchMock = vi.fn<typeof fetch>()

describe('request', () => {
  beforeEach(() => {
    vi.stubGlobal('fetch', fetchMock)
    fetchMock.mockReset()
  })
  afterEach(() => vi.unstubAllGlobals())

  it('sends the acting user and a JSON body', async () => {
    setActingUserId('user-1')
    fetchMock.mockResolvedValue(jsonResponse({ ok: true }, 201))
    await expect(request('/api/rfqs', { method: 'POST', body: { name: 'x' } })).resolves.toEqual({ ok: true })

    const [url, init] = fetchMock.mock.calls[0]
    expect(url).toBe('/api/rfqs')
    expect(init?.method).toBe('POST')
    expect(init?.body).toBe('{"name":"x"}')
    expect(init?.headers).toMatchObject({ 'X-User-Id': 'user-1', 'Content-Type': 'application/json' })
  })

  it('omits the user header when nobody is selected', async () => {
    fetchMock.mockResolvedValue(jsonResponse({}))
    await request('/api/users')
    expect(fetchMock.mock.calls[0][1]?.headers).not.toHaveProperty('X-User-Id')
  })

  it('records server_time for the server clock', async () => {
    const serverTime = new Date(Date.now() + 60_000).toISOString()
    fetchMock.mockResolvedValue(jsonResponse({ server_time: serverTime }))
    await request('/api/meta/time')
    expect(clockOffsetMs()).toBeGreaterThan(59_000)
  })

  it('turns the error envelope into an ApiError', async () => {
    fetchMock.mockResolvedValue(
      jsonResponse(
        {
          error: {
            code: 'FORCED_CLOSE_NOT_AFTER_CLOSE',
            message: 'Forced close time must be later than the bid close time.',
            details: [
              { field: 'forced_close_at', message: 'Must be later than bid_close_at' },
              { field: 'forced_close_at', message: 'second message is ignored' },
              { field: null, message: 'not tied to a field' },
            ],
          },
          server_time: '2026-11-07T12:00:00Z',
        },
        422,
      ),
    )
    const error = await request('/api/rfqs').catch((e: unknown) => e)
    expect(error).toBeInstanceOf(ApiError)
    expect(error).toMatchObject({ status: 422, code: 'FORCED_CLOSE_NOT_AFTER_CLOSE' })
    expect((error as ApiError).fieldErrors()).toEqual({ forced_close_at: 'Must be later than bid_close_at' })
    expect(errorMessage(error)).toBe('The forced close must be later than the bid close time.')
  })

  it('copes with errors that are not JSON', async () => {
    fetchMock.mockResolvedValue(new Response('<html>Bad gateway</html>', { status: 502 }))
    const error = await request('/api/rfqs').catch((e: unknown) => e)
    expect(error).toMatchObject({ status: 502, code: 'HTTP_502', message: 'Request failed (502)' })
  })

  it('reports network failures as NETWORK_ERROR', async () => {
    fetchMock.mockRejectedValue(new TypeError('Failed to fetch'))
    const error = await request('/api/rfqs').catch((e: unknown) => e)
    expect(error).toMatchObject({ status: 0, code: 'NETWORK_ERROR' })
    expect(errorMessage(error)).toMatch(/Can’t reach the server/)
  })

  it('lets aborts through unchanged', async () => {
    fetchMock.mockRejectedValue(new DOMException('aborted', 'AbortError'))
    await expect(request('/api/rfqs')).rejects.toMatchObject({ name: 'AbortError' })
  })
})

describe('buildUrl', () => {
  it('skips empty parameters and encodes values', () => {
    expect(buildUrl('/api/rfqs')).toBe('/api/rfqs')
    expect(buildUrl('/api/rfqs', { status: 'ACTIVE', search: '', page: 2, x: undefined, y: null })).toBe(
      '/api/rfqs?status=ACTIVE&page=2',
    )
    expect(buildUrl('/api/rfqs', { search: 'Mumbai & Co' })).toBe('/api/rfqs?search=Mumbai+%26+Co')
  })
})

describe('errorMessage', () => {
  it('falls back to the server message for unknown codes', () => {
    expect(errorMessage(new ApiError(409, 'SOMETHING_NEW', 'Server says no'))).toBe('Server says no')
    expect(errorMessage(new Error('boom'))).toBe('boom')
    expect(errorMessage('weird')).toBe('Something went wrong.')
  })
})
