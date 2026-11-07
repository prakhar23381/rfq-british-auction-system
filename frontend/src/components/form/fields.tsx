import type { ReactNode } from 'react'

import { cx } from '../ui/cx'
import { inputClasses } from './inputClasses'

export interface ControlProps {
  id: string
  'aria-invalid'?: boolean
  'aria-describedby'?: string
}

interface FieldProps {
  id: string
  label: ReactNode
  hint?: ReactNode
  error?: string
  optional?: boolean
  className?: string
  children: (control: ControlProps) => ReactNode
}

/** Label, control, and a hint that is replaced by the error when there is one. */
export function Field({ id, label, hint, error, optional, className, children }: FieldProps) {
  const describedBy = error ? `${id}-error` : hint ? `${id}-hint` : undefined
  return (
    <div className={cx('min-w-0', className)}>
      <label htmlFor={id} className="mb-1.5 flex items-baseline gap-2 text-[13px] font-medium text-ink-2">
        {label}
        {optional && <span className="font-mono text-[10px] tracking-[0.08em] text-ink-3 uppercase">optional</span>}
      </label>
      {children({ id, 'aria-invalid': error ? true : undefined, 'aria-describedby': describedBy })}
      {error ? (
        <p id={`${id}-error`} className="mt-1.5 text-xs leading-snug text-danger">
          {error}
        </p>
      ) : (
        hint && (
          <p id={`${id}-hint`} className="mt-1.5 text-xs leading-snug text-ink-3">
            {hint}
          </p>
        )
      )}
    </div>
  )
}

/** A number input with a unit inside the box ("10 min"). */
export function UnitInput({
  unit,
  value,
  onChange,
  onBlur,
  control,
  min,
  max,
  disabled,
}: {
  unit: string
  value: string
  onChange: (value: string) => void
  onBlur?: () => void
  control: ControlProps
  min?: number
  max?: number
  disabled?: boolean
}) {
  return (
    <div className="relative">
      <input
        {...control}
        type="number"
        inputMode="numeric"
        min={min}
        max={max}
        step={1}
        disabled={disabled}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onBlur={onBlur}
        className={cx(inputClasses, 'pr-12 font-mono tabular-nums')}
      />
      <span aria-hidden className="pointer-events-none absolute inset-y-0 right-3 flex items-center font-mono text-xs text-ink-3">
        {unit}
      </span>
    </div>
  )
}

/** A switch that is always on (British auction is the only mode this app runs). */
export function LockedSwitch({ id, label, description }: { id: string; label: string; description: string }) {
  return (
    <div className="flex items-start justify-between gap-4">
      <div>
        <p id={`${id}-label`} className="text-sm font-medium text-ink">
          {label}
        </p>
        <p id={`${id}-description`} className="mt-0.5 text-xs text-ink-3">
          {description}
        </p>
      </div>
      <button
        id={id}
        type="button"
        role="switch"
        aria-checked="true"
        aria-disabled="true"
        aria-labelledby={`${id}-label`}
        aria-describedby={`${id}-description`}
        className="relative mt-0.5 inline-flex h-6 w-11 shrink-0 cursor-not-allowed items-center rounded-full bg-peri/80 opacity-90"
      >
        <span aria-hidden className="absolute right-0.5 size-5 rounded-full bg-white shadow" />
      </button>
    </div>
  )
}
