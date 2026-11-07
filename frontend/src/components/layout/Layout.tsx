import type { ReactNode } from 'react'
import { Link, NavLink, Outlet, useLocation, useSearchParams } from 'react-router'

import type { AuctionStatus } from '../../api/types'
import { STATUS_LABELS } from '../../lib/format'
import { useActingUser } from '../../user/userContext'
import { Eyebrow } from '../ui/Card'
import { cx } from '../ui/cx'
import { ActingAsMenu } from './ActingAsMenu'
import { ConnectionChip, SystemStatus } from './StatusIndicators'

const STATUS_DOTS: Array<[AuctionStatus, string]> = [
  ['ACTIVE', 'bg-mint'],
  ['SCHEDULED', 'bg-lilac'],
  ['CLOSED', 'bg-peri-2'],
  ['FORCE_CLOSED', 'bg-rose'],
]

const icons = {
  auctions: (
    <svg aria-hidden viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4">
      <path d="M4 6h16M4 12h16M4 18h10" />
    </svg>
  ),
  create: (
    <svg aria-hidden viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.4">
      <path d="M12 5v14M5 12h14" />
    </svg>
  ),
}

function navItemClasses(active: boolean): string {
  return cx(
    'flex items-center gap-2.5 rounded-lg px-2.5 py-2 text-sm transition-colors [&_svg]:size-4 [&_svg]:opacity-80',
    active
      ? 'bg-violet/15 text-ink shadow-[inset_2px_0_0] shadow-peri-2'
      : 'text-ink-2 hover:bg-white/[0.05] hover:text-ink',
  )
}

function SidebarLink({ to, icon, children }: { to: string; icon: ReactNode; children: ReactNode }) {
  const { search } = useLocation()
  return (
    <NavLink to={to} end className={({ isActive }) => navItemClasses(isActive && (to !== '/' || !search))}>
      {icon}
      {children}
    </NavLink>
  )
}

function Sidebar({ isBuyer }: { isBuyer: boolean }) {
  const { pathname } = useLocation()
  const [params] = useSearchParams()
  const currentStatus = pathname === '/' ? params.get('status') : null

  return (
    <aside className="hidden w-56 shrink-0 lg:block">
      <nav aria-label="Main" className="sticky top-24 flex flex-col gap-0.5">
        <Eyebrow className="mb-1.5 px-2.5">Workspace</Eyebrow>
        <SidebarLink to="/" icon={icons.auctions}>
          Auctions
        </SidebarLink>
        {isBuyer && (
          <SidebarLink to="/rfqs/new" icon={icons.create}>
            Create RFQ
          </SidebarLink>
        )}

        <Eyebrow className="mt-6 mb-1.5 px-2.5">By status</Eyebrow>
        {STATUS_DOTS.map(([status, dot]) => (
          <Link
            key={status}
            to={`/?status=${status}`}
            aria-current={currentStatus === status ? 'page' : undefined}
            className={navItemClasses(currentStatus === status)}
          >
            <span aria-hidden className={cx('mx-[5px] size-1.5 rounded-full', dot)} />
            {STATUS_LABELS[status]}
          </Link>
        ))}

        <div className="mt-8 px-2.5">
          <SystemStatus />
        </div>
      </nav>
    </aside>
  )
}

function MobileNav({ isBuyer }: { isBuyer: boolean }) {
  const { search } = useLocation()
  const tab = (active: boolean) =>
    cx(
      'rounded-md px-3 py-1.5 text-[13px] transition-colors',
      active ? 'bg-white/10 text-ink' : 'text-ink-2 hover:text-ink',
    )
  return (
    <nav aria-label="Main" className="border-t border-line-soft lg:hidden">
      <div className="mx-auto flex max-w-[1400px] items-center gap-1 px-4 py-2 sm:px-6">
        <NavLink to="/" end className={({ isActive }) => tab(isActive && !search)}>
          Auctions
        </NavLink>
        {isBuyer && (
          <NavLink to="/rfqs/new" className={({ isActive }) => tab(isActive)}>
            Create RFQ
          </NavLink>
        )}
      </div>
    </nav>
  )
}

export function Layout() {
  const { user } = useActingUser()
  const isBuyer = user?.role === 'BUYER'

  return (
    <div className="flex min-h-dvh flex-col">
      <a
        href="#main"
        className="sr-only z-50 rounded-md bg-peri px-3 py-2 text-white focus:not-sr-only focus:fixed focus:top-3 focus:left-3"
      >
        Skip to content
      </a>
      <header className="sticky top-0 z-30 border-b border-line bg-[rgb(13_8_48/0.72)] backdrop-blur-xl backdrop-saturate-150">
        <div className="mx-auto flex h-16 max-w-[1400px] items-center gap-3 px-4 sm:px-6">
          <Link to="/" className="flex shrink-0 items-center gap-2.5 text-[15px] font-semibold whitespace-nowrap sm:text-[17px] tracking-[-0.01em] text-ink">
            <span aria-hidden className="orb size-6" />
            <span>
              British Auction <span className="hidden font-light text-ink-2 sm:inline">RFQ</span>
            </span>
          </Link>
          <div className="flex-1" />
          <ConnectionChip />
          <ActingAsMenu />
        </div>
        <MobileNav isBuyer={isBuyer} />
      </header>

      <div className="mx-auto flex w-full max-w-[1400px] flex-1 gap-8 px-4 py-6 sm:px-6 lg:py-10">
        <Sidebar isBuyer={isBuyer} />
        <main id="main" className="min-w-0 flex-1">
          <Outlet />
        </main>
      </div>
    </div>
  )
}
