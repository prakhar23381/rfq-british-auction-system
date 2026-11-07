import { useEffect, useRef } from 'react'

import { cx } from './cx'

interface SearchInputProps {
  value: string
  onChange: (value: string) => void
  label: string
  placeholder?: string
  className?: string
}

/** Search box; "/" anywhere on the page focuses it. */
export function SearchInput({ value, onChange, label, placeholder, className }: SearchInputProps) {
  const ref = useRef<HTMLInputElement>(null)

  useEffect(() => {
    const onKeyDown = (event: KeyboardEvent) => {
      if (event.key !== '/' || event.metaKey || event.ctrlKey || event.altKey) return
      const target = event.target as HTMLElement | null
      if (target?.closest('input, textarea, select, [contenteditable="true"]')) return
      event.preventDefault()
      ref.current?.focus()
    }
    document.addEventListener('keydown', onKeyDown)
    return () => document.removeEventListener('keydown', onKeyDown)
  }, [])

  return (
    <label
      className={cx(
        'flex h-9 items-center gap-2 rounded-lg border border-[rgb(190_170_255/0.12)] bg-[rgb(170_150_255/0.07)] px-2.5 text-ink-3 transition-colors focus-within:border-peri-2/60',
        className,
      )}
    >
      <svg aria-hidden viewBox="0 0 16 16" className="size-3.5 shrink-0" fill="none" stroke="currentColor" strokeWidth="1.5">
        <circle cx="7" cy="7" r="4.5" />
        <path d="M10.5 10.5L14 14" />
      </svg>
      <input
        ref={ref}
        type="search"
        aria-label={label}
        value={value}
        onChange={(event) => onChange(event.target.value)}
        onKeyDown={(event) => {
          if (event.key === 'Escape' && value) {
            event.preventDefault()
            onChange('')
          }
        }}
        placeholder={placeholder}
        maxLength={100}
        className="min-w-0 flex-1 bg-transparent text-[13px] text-ink outline-none placeholder:text-ink-3 [&::-webkit-search-cancel-button]:hidden"
      />
      {value ? (
        <button
          type="button"
          onClick={() => {
            onChange('')
            ref.current?.focus()
          }}
          className="rounded p-0.5 text-ink-3 hover:text-ink"
          aria-label="Clear search"
        >
          <svg aria-hidden viewBox="0 0 16 16" className="size-3" stroke="currentColor" strokeWidth="1.6">
            <path d="M4 4l8 8M12 4l-8 8" />
          </svg>
        </button>
      ) : (
        <kbd className="hidden rounded bg-white/[0.06] px-1.5 font-mono text-[10px] text-ink-3 sm:block">/</kbd>
      )}
    </label>
  )
}
