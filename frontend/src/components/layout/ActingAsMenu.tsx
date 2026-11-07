import { useEffect, useId, useRef, useState, type KeyboardEvent } from 'react'

import type { User } from '../../api/types'
import { initials } from '../../lib/format'
import { useActingUser } from '../../user/userContext'
import { Chip } from '../ui/Chip'
import { cx } from '../ui/cx'
import { useToast } from '../ui/toastContext'

const ROLE_LABEL = { BUYER: 'Buyer', SUPPLIER: 'Supplier' } as const

function Avatar({ user, size = 'md' }: { user: User; size?: 'sm' | 'md' }) {
  return (
    <span
      aria-hidden
      className={cx(
        'grid shrink-0 place-items-center rounded-full font-semibold text-white',
        user.role === 'BUYER'
          ? 'bg-gradient-to-br from-violet-deep to-peri'
          : 'bg-gradient-to-br from-violet-deep to-rose',
        size === 'md' ? 'size-8 text-[11px]' : 'size-7 text-[10px]',
      )}
    >
      {initials(user.company_name)}
    </span>
  )
}

/** "Acting as" switcher: a menu of the seeded users, grouped into buyers and suppliers. */
export function ActingAsMenu() {
  const { user, users, isLoading, error, retry, setUserId } = useActingUser()
  const toast = useToast()
  const [open, setOpen] = useState(false)
  const rootRef = useRef<HTMLDivElement>(null)
  const buttonRef = useRef<HTMLButtonElement>(null)
  const menuRef = useRef<HTMLDivElement>(null)
  const menuId = useId()

  const items = () => [...(menuRef.current?.querySelectorAll<HTMLElement>('[role="menuitemradio"]') ?? [])]

  useEffect(() => {
    if (!open) return
    const checked = menuRef.current?.querySelector<HTMLElement>('[aria-checked="true"]')
    ;(checked ?? items()[0])?.focus()
    const onPointerDown = (event: PointerEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('pointerdown', onPointerDown)
    return () => document.removeEventListener('pointerdown', onPointerDown)
  }, [open])

  const close = (focusButton: boolean) => {
    setOpen(false)
    if (focusButton) buttonRef.current?.focus()
  }

  const choose = (next: User) => {
    close(true)
    if (next.id === user?.id) return
    setUserId(next.id)
    toast.show({
      tone: 'info',
      title: `Acting as ${next.company_name}`,
      description: `${next.name} · ${ROLE_LABEL[next.role]}`,
      duration: 3000,
    })
  }

  const onMenuKeyDown = (event: KeyboardEvent) => {
    const list = items()
    const index = list.indexOf(document.activeElement as HTMLElement)
    const focusAt = (i: number) => list[(i + list.length) % list.length]?.focus()
    switch (event.key) {
      case 'ArrowDown':
        event.preventDefault()
        focusAt(index + 1)
        break
      case 'ArrowUp':
        event.preventDefault()
        focusAt(index - 1)
        break
      case 'Home':
        event.preventDefault()
        focusAt(0)
        break
      case 'End':
        event.preventDefault()
        focusAt(list.length - 1)
        break
      case 'Escape':
        event.preventDefault()
        close(true)
        break
      case 'Tab':
        close(false)
        break
    }
  }

  if (error && users.length === 0) {
    return (
      <button
        type="button"
        onClick={retry}
        className="rounded-lg border border-danger/30 px-3 py-1.5 font-mono text-xs text-danger"
      >
        Users unavailable · retry
      </button>
    )
  }
  if (isLoading || !user) {
    return (
      <span className="font-mono text-xs text-ink-3">
        {isLoading ? 'Loading users…' : 'No users · run make seed'}
      </span>
    )
  }

  const groups = [
    { label: 'Buyers', members: users.filter((u) => u.role === 'BUYER') },
    { label: 'Suppliers', members: users.filter((u) => u.role === 'SUPPLIER') },
  ].filter((group) => group.members.length > 0)

  return (
    <div ref={rootRef} className="relative">
      <button
        ref={buttonRef}
        type="button"
        aria-haspopup="menu"
        aria-expanded={open}
        aria-controls={open ? menuId : undefined}
        onClick={() => setOpen((value) => !value)}
        onKeyDown={(event) => {
          if (event.key === 'ArrowDown' && !open) {
            event.preventDefault()
            setOpen(true)
          }
        }}
        className="flex items-center gap-2.5 rounded-xl border border-line bg-white/[0.03] py-1 pr-2.5 pl-1 transition-colors hover:bg-white/[0.07]"
      >
        <Avatar user={user} />
        <span className="hidden min-w-0 text-left leading-tight md:block">
          <span className="block font-mono text-[10px] tracking-[0.08em] text-ink-3 uppercase">Acting as</span>
          <span className="block max-w-40 truncate text-[13px] text-ink">{user.company_name}</span>
        </span>
        <span className="hidden sm:block">
          <Chip tone={user.role === 'BUYER' ? 'peri' : 'rose'}>{ROLE_LABEL[user.role]}</Chip>
        </span>
        <svg aria-hidden viewBox="0 0 10 10" className="size-2.5 text-ink-3" fill="none" stroke="currentColor" strokeWidth="1.4">
          <path d="M2 3.5l3 3 3-3" />
        </svg>
        <span className="sr-only">
          Acting as {user.company_name} ({ROLE_LABEL[user.role]}). Change user
        </span>
      </button>

      {open && (
        <div
          ref={menuRef}
          id={menuId}
          role="menu"
          aria-label="Act as"
          onKeyDown={onMenuKeyDown}
          className="popover absolute right-0 z-40 mt-2 max-h-[70vh] w-72 max-w-[calc(100vw-2rem)] animate-rise overflow-y-auto rounded-xl p-1.5"
        >
          {groups.map((group) => (
            <div key={group.label} role="group" aria-label={group.label} className="py-1">
              <p className="px-2.5 pt-1 pb-1.5 font-mono text-[10px] tracking-[0.1em] text-ink-3 uppercase">
                {group.label}
              </p>
              {group.members.map((member) => {
                const checked = member.id === user.id
                return (
                  <button
                    key={member.id}
                    type="button"
                    role="menuitemradio"
                    aria-checked={checked}
                    tabIndex={-1}
                    onClick={() => choose(member)}
                    className={cx(
                      'flex w-full items-center gap-2.5 rounded-lg px-2.5 py-2 text-left transition-colors outline-none',
                      'hover:bg-white/[0.07] focus-visible:bg-white/[0.09]',
                      checked && 'bg-violet/15 shadow-[inset_2px_0_0] shadow-peri-2',
                    )}
                  >
                    <Avatar user={member} size="sm" />
                    <span className="min-w-0 flex-1">
                      <span className="block truncate text-[13px] text-ink">{member.company_name}</span>
                      <span className="block truncate text-xs text-ink-3">{member.name}</span>
                    </span>
                    {checked && (
                      <svg aria-hidden viewBox="0 0 16 16" className="size-3.5 text-peri-2" fill="none" stroke="currentColor" strokeWidth="1.8">
                        <path d="M3 8.5l3 3 7-7" />
                      </svg>
                    )}
                  </button>
                )
              })}
            </div>
          ))}
        </div>
      )}
    </div>
  )
}
