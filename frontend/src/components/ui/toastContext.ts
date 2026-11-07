import { createContext, useContext } from 'react'

export type ToastTone = 'success' | 'error' | 'info' | 'time'

export interface ToastInput {
  tone?: ToastTone
  title: string
  description?: string
  /** Milliseconds; 0 keeps it until dismissed. */
  duration?: number
}

export interface Toast extends Required<Omit<ToastInput, 'description'>> {
  id: number
  description?: string
}

export interface ToastContextValue {
  show: (toast: ToastInput) => number
  dismiss: (id: number) => void
}

export const ToastContext = createContext<ToastContextValue | null>(null)

export function useToast(): ToastContextValue {
  const context = useContext(ToastContext)
  if (!context) throw new Error('useToast must be used inside <ToastProvider>')
  return context
}
