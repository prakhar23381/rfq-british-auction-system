import { useEffect, useState } from 'react'

type CheckStatus = 'ok' | 'error'

interface Health {
  status: CheckStatus
  db: CheckStatus
  redis: CheckStatus
  server_time: string
}

type LoadState =
  | { kind: 'loading' }
  | { kind: 'ready'; health: Health }
  | { kind: 'failed'; message: string }

function App() {
  const [state, setState] = useState<LoadState>({ kind: 'loading' })

  useEffect(() => {
    fetch('/api/health')
      .then(async (res) => {
        if (!res.ok) throw new Error(`HTTP ${res.status}`)
        setState({ kind: 'ready', health: (await res.json()) as Health })
      })
      .catch((err: unknown) =>
        setState({ kind: 'failed', message: err instanceof Error ? err.message : String(err) }),
      )
  }, [])

  return (
    <main className="shell">
      <h1>British Auction RFQ</h1>
      <p className="muted">Backend status</p>
      {state.kind === 'loading' && <p>Checking…</p>}
      {state.kind === 'failed' && <p className="bad">Backend unreachable: {state.message}</p>}
      {state.kind === 'ready' && (
        <ul className="checks">
          <li className={state.health.status}>API: {state.health.status}</li>
          <li className={state.health.db}>Database: {state.health.db}</li>
          <li className={state.health.redis}>Redis: {state.health.redis}</li>
          <li className="muted">Server time: {new Date(state.health.server_time).toLocaleString()}</li>
        </ul>
      )}
    </main>
  )
}

export default App
