import { act, fireEvent, render, screen } from '@testing-library/react'
import userEvent from '@testing-library/user-event'
import { useState } from 'react'
import { MemoryRouter } from 'react-router'
import { afterEach, describe, expect, it, vi } from 'vitest'

import { ScheduleTimeline } from '../ScheduleTimeline'
import { DataTable } from './DataTable'
import { Pagination } from './Pagination'
import { SearchInput } from './SearchInput'
import { SegmentedControl } from './SegmentedControl'
import { ToastProvider } from './Toast'
import { useToast } from './toastContext'
import { Countdown, DateTime, Money } from './values'

afterEach(() => vi.useRealTimers())

function Search() {
  const [value, setValue] = useState('')
  return (
    <>
      <input aria-label="Other field" />
      <SearchInput value={value} onChange={setValue} label="Search" />
    </>
  )
}

describe('SearchInput', () => {
  it('"/" focuses it, except while typing elsewhere', async () => {
    render(<Search />)
    const search = screen.getByRole('searchbox', { name: 'Search' })
    await userEvent.keyboard('/')
    expect(search).toHaveFocus()
    expect(search).toHaveValue('') // the slash is not typed

    await userEvent.click(screen.getByRole('textbox', { name: 'Other field' }))
    await userEvent.keyboard('/')
    expect(screen.getByRole('textbox', { name: 'Other field' })).toHaveValue('/')
    expect(search).not.toHaveFocus()

    // With a modifier it is left to the browser.
    fireEvent.keyDown(document.body, { key: '/', metaKey: true })
    expect(search).not.toHaveFocus()
  })

  it('clears with Escape or the clear button', async () => {
    render(<Search />)
    const search = screen.getByRole('searchbox', { name: 'Search' })
    await userEvent.type(search, 'dubai')
    await userEvent.keyboard('{Escape}')
    expect(search).toHaveValue('')

    await userEvent.type(search, 'pune')
    await userEvent.click(screen.getByRole('button', { name: 'Clear search' }))
    expect(search).toHaveValue('')
    expect(search).toHaveFocus()
  })
})

describe('Pagination', () => {
  it('moves both ways and hides when everything fits', async () => {
    const onChange = vi.fn()
    const { rerender, container } = render(<Pagination page={2} pageSize={20} total={45} onChange={onChange} />)
    expect(screen.getByText('21–40 of 45')).toBeInTheDocument()
    await userEvent.click(screen.getByRole('button', { name: '← Previous' }))
    await userEvent.click(screen.getByRole('button', { name: 'Next →' }))
    expect(onChange.mock.calls).toEqual([[1], [3]])

    rerender(<Pagination page={3} pageSize={20} total={45} onChange={onChange} />)
    expect(screen.getByText('41–45 of 45')).toBeInTheDocument()
    expect(screen.getByRole('button', { name: 'Next →' })).toBeDisabled()

    rerender(<Pagination page={1} pageSize={20} total={5} onChange={onChange} />)
    expect(container).toBeEmptyDOMElement()
  })
})

function ToastButtons() {
  const toast = useToast()
  return (
    <>
      <button onClick={() => toast.show({ title: 'Saved', tone: 'success' })}>short</button>
      <button onClick={() => toast.show({ title: 'Sticky', tone: 'error', duration: 0 })}>sticky</button>
      <button onClick={() => [1, 2, 3, 4].forEach((n) => toast.show({ title: `Toast ${n}` }))}>many</button>
    </>
  )
}

describe('Toasts', () => {
  it('disappear on their own, can be dismissed, and never pile up past three', async () => {
    vi.useFakeTimers({ shouldAdvanceTime: true })
    render(
      <ToastProvider>
        <ToastButtons />
      </ToastProvider>,
    )
    fireEvent.click(screen.getByText('short'))
    expect(screen.getByRole('status')).toHaveTextContent('Saved')
    act(() => {
      vi.advanceTimersByTime(5000)
    })
    expect(screen.queryByText('Saved')).not.toBeInTheDocument()

    fireEvent.click(screen.getByText('sticky'))
    expect(screen.getByRole('alert')).toHaveTextContent('Sticky') // errors are announced assertively
    act(() => {
      vi.advanceTimersByTime(60_000)
    })
    expect(screen.getByText('Sticky')).toBeInTheDocument()
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss notification' }))
    expect(screen.queryByText('Sticky')).not.toBeInTheDocument()

    fireEvent.click(screen.getByText('many'))
    expect(screen.queryByText('Toast 1')).not.toBeInTheDocument()
    expect(screen.getAllByText(/Toast [234]/)).toHaveLength(3)
  })

  it('useToast outside the provider is a programming error', () => {
    const spy = vi.spyOn(console, 'error').mockImplementation(() => {})
    expect(() => render(<ToastButtons />)).toThrow('inside <ToastProvider>')
    spy.mockRestore()
  })
})

describe('value components', () => {
  it('render placeholders for missing values', () => {
    render(
      <>
        <Money amount={null} fallback="No bids yet" />
        <DateTime value={null} />
        <Countdown target="2026-01-01T00:00:00Z" overLabel="Closing…" />
      </>,
    )
    expect(screen.getByText('No bids yet')).toHaveClass('text-ink-3')
    expect(screen.getByText('—')).toBeInTheDocument()
    expect(screen.getByText('Closing…')).toBeInTheDocument()
  })
})

describe('SegmentedControl', () => {
  it('wraps around with the arrow keys', async () => {
    function Tabs() {
      const [value, setValue] = useState<'a' | 'b' | 'c'>('a')
      return (
        <SegmentedControl
          label="Tabs"
          value={value}
          onChange={setValue}
          segments={[
            { value: 'a', label: 'A', count: 1 },
            { value: 'b', label: 'B' },
            { value: 'c', label: 'C', dot: 'bg-mint' },
          ]}
        />
      )
    }
    render(<Tabs />)
    screen.getByRole('radio', { name: /A/ }).focus()
    await userEvent.keyboard('{ArrowLeft}')
    expect(screen.getByRole('radio', { name: 'C' })).toHaveAttribute('aria-checked', 'true')
    expect(screen.getByRole('radio', { name: 'C' })).toHaveFocus()
    await userEvent.keyboard('{ArrowRight}{ArrowRight}')
    expect(screen.getByRole('radio', { name: 'B' })).toHaveAttribute('aria-checked', 'true')
    await userEvent.keyboard('{Enter}x')
    expect(screen.getByRole('radio', { name: 'B' })).toHaveAttribute('aria-checked', 'true')
  })
})

describe('DataTable', () => {
  it('renders a table and phone cards with labels', () => {
    render(
      <MemoryRouter>
        <DataTable
          caption="People"
          rows={[{ id: '1', name: 'Asha', city: 'Pune', secret: 'x' }]}
          rowKey={(r) => r.id}
          columns={[
            { key: 'name', header: 'Name', primary: true, cell: (r) => r.name },
            { key: 'city', header: 'City', mobileLabel: 'Town', cell: (r) => r.city },
            { key: 'secret', header: 'Secret', mobileLabel: false, cell: (r) => r.secret, align: 'right' },
          ]}
        />
      </MemoryRouter>,
    )
    expect(screen.getByRole('table', { name: 'People' })).toHaveTextContent('AshaPunex')
    const cards = screen.getByRole('list', { name: 'People' })
    expect(cards).toHaveTextContent('Town')
    expect(cards).not.toHaveTextContent('Secret')
  })
})

describe('ScheduleTimeline', () => {
  const at = (m: number) => Date.UTC(2026, 10, 7, 12, m)

  it('describes the schedule and refuses impossible ones', () => {
    const { rerender, container } = render(
      <ScheduleTimeline startMs={at(0)} closeMs={at(30)} forcedMs={at(40)} windowMinutes={10} nowMs={at(25)} />,
    )
    expect(screen.getByRole('img')).toHaveAccessibleName(/^Bidding \d\d:\d\d to \d\d:\d\d, trigger window from \d\d:\d\d, extensions possible until \d\d:\d\d$/)
    rerender(<ScheduleTimeline startMs={at(0)} closeMs={at(50)} forcedMs={at(40)} windowMinutes={10} />)
    expect(container).toBeEmptyDOMElement()
  })
})
