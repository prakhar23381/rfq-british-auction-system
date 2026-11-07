import { useCallback, useMemo, useRef, useState, type ReactNode } from 'react'

import { cx } from './cx'
import { type Toast, ToastContext, type ToastInput, type ToastTone } from './toastContext'

const TONE: Record<ToastTone, { bar: string; icon: string }> = {
  success: { bar: 'bg-mint', icon: '✓' },
  error: { bar: 'bg-danger', icon: '!' },
  info: { bar: 'bg-peri-2', icon: 'i' },
  time: { bar: 'bg-amber', icon: '◷' },
}

const MAX_TOASTS = 4

export function ToastProvider({ children }: { children: ReactNode }) {
  const [toasts, setToasts] = useState<Toast[]>([])
  const nextId = useRef(1)
  const timers = useRef(new Map<number, ReturnType<typeof setTimeout>>())

  const dismiss = useCallback((id: number) => {
    clearTimeout(timers.current.get(id))
    timers.current.delete(id)
    setToasts((current) => current.filter((toast) => toast.id !== id))
  }, [])

  const show = useCallback(
    ({ tone = 'info', title, description, duration = 5000 }: ToastInput) => {
      const id = nextId.current++
      setToasts((current) => [...current, { id, tone, title, description, duration }].slice(-MAX_TOASTS))
      if (duration > 0) timers.current.set(id, setTimeout(() => dismiss(id), duration))
      return id
    },
    [dismiss],
  )

  const value = useMemo(() => ({ show, dismiss }), [show, dismiss])

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div
        aria-live="polite"
        className="pointer-events-none fixed inset-x-4 bottom-4 z-50 flex flex-col items-center gap-2 sm:inset-x-auto sm:right-6 sm:bottom-6 sm:items-end"
      >
        {toasts.map((toast) => (
          <div
            key={toast.id}
            role={toast.tone === 'error' ? 'alert' : 'status'}
            className="popover pointer-events-auto relative flex w-full max-w-sm animate-rise items-start gap-3 overflow-hidden rounded-xl py-3 pr-3 pl-4"
          >
            <span aria-hidden className={cx('absolute inset-y-0 left-0 w-[3px]', TONE[toast.tone].bar)} />
            <span aria-hidden className="mt-0.5 w-3 shrink-0 text-center font-mono text-xs text-ink-2">
              {TONE[toast.tone].icon}
            </span>
            <div className="min-w-0 flex-1">
              <p className="text-sm font-medium text-ink">{toast.title}</p>
              {toast.description && <p className="mt-0.5 text-[13px] text-ink-2">{toast.description}</p>}
            </div>
            <button
              type="button"
              onClick={() => dismiss(toast.id)}
              className="-m-1 rounded p-1 text-ink-3 transition-colors hover:text-ink"
              aria-label="Dismiss notification"
            >
              <svg aria-hidden viewBox="0 0 16 16" className="size-3.5" stroke="currentColor" strokeWidth="1.6">
                <path d="M4 4l8 8M12 4l-8 8" />
              </svg>
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  )
}
