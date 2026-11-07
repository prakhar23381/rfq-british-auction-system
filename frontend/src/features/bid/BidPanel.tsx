import { useMutation, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useState } from 'react'

import { ApiError } from '../../api/client'
import { api, queryKeys } from '../../api/endpoints'
import { errorMessage } from '../../api/errors'
import type { RfqDetail, User } from '../../api/types'
import { Field, UnitInput } from '../../components/form/fields'
import { inputClasses } from '../../components/form/inputClasses'
import { Button } from '../../components/ui/Button'
import { Card } from '../../components/ui/Card'
import { cx } from '../../components/ui/cx'
import { useToast } from '../../components/ui/toastContext'
import { DateTime, Money } from '../../components/ui/values'
import { useCountdown } from '../../hooks/useCountdown'
import { formatTime } from '../../lib/format'
import { centsToAmount } from '../../lib/money'
import { useActingUser } from '../../user/userContext'
import {
  BID_FIELD_ORDER,
  type BidErrors,
  type BidField,
  type BidFormValues,
  bidFieldId,
  bidServerErrors,
  initialBidValues,
  toBidPayload,
  totalCents,
  validateBid,
} from './bidForm'

const QUALIFYING = {
  BID_RECEIVED: 'Any bid now',
  ANY_RANK_CHANGE: 'A bid that changes the ranking',
  L1_CHANGE: 'A bid that takes L1',
} as const

/** Shown instead of the form to buyers: one click switches to a supplier. */
function BuyerNote() {
  const { users, setUserId } = useActingUser()
  const supplier = users.find((u) => u.role === 'SUPPLIER')
  return (
    <Card title="Place a bid">
      <p className="text-sm text-ink-2">You’re viewing as the buyer. Suppliers bid here, and you watch the ranking change live.</p>
      {supplier && (
        <Button variant="subtle" size="sm" className="mt-4" onClick={() => setUserId(supplier.id)}>
          Act as {supplier.company_name}
        </Button>
      )}
    </Card>
  )
}

export function BidPanel({ detail }: { detail: RfqDetail }) {
  const { user } = useActingUser()
  if (!user) return null
  if (user.role !== 'SUPPLIER') return <BuyerNote />
  // Re-mount for each supplier so the form starts from their own bid.
  return <BidForm key={user.id} detail={detail} user={user} />
}

function BidForm({ detail, user }: { detail: RfqDetail; user: User }) {
  const { rfq, auction_config: config, ranking } = detail
  const previous = ranking.find((row) => row.supplier.id === user.id)
  const queryClient = useQueryClient()
  const toast = useToast()

  const [values, setValues] = useState<BidFormValues>(() => initialBidValues(previous, rfq.pickup_date))
  const [submitted, setSubmitted] = useState(false)
  const [touched, setTouched] = useState<ReadonlySet<BidField>>(() => new Set())
  const [fromServer, setFromServer] = useState<BidErrors>({})
  const [banner, setBanner] = useState<string | null>(null)

  const countdown = useCountdown(rfq.current_close_at, config.trigger_window_minutes)
  const open = rfq.status === 'ACTIVE' && !countdown.isOver

  const errors = validateBid(values, { pickupDate: rfq.pickup_date, previousTotal: previous?.total_amount ?? null })
  const shown = (field: BidField) => fromServer[field] ?? (submitted || touched.has(field) ? errors[field] : undefined)
  const total = totalCents(values)

  const set = (field: keyof BidFormValues, value: string) => {
    setValues((current) => ({ ...current, [field]: value }))
    setFromServer((current) => {
      const next = { ...current }
      delete next[field]
      if (field === 'freight' || field === 'origin' || field === 'destination') delete next.total
      return next
    })
  }
  const touch = (field: BidField) => () => setTouched((current) => new Set(current).add(field))
  const focus = (field: BidField) => document.getElementById(bidFieldId(field === 'total' ? 'freight' : field))?.focus()

  const submit = useMutation({
    mutationFn: () => api.submitBid(rfq.id, toBidPayload(values)),
    onSuccess: (result) => {
      setSubmitted(false)
      setTouched(new Set())
      const extension = result.extension
      let description: string | undefined
      if (extension?.applied) {
        description = `Auction extended to ${formatTime(extension.new_close_at)}${extension.capped ? ' (capped at the forced close)' : ''}.`
      } else if (extension?.capped) {
        description = 'The close is already at the forced close, so no extension.'
      }
      toast.show({ tone: extension?.applied ? 'time' : 'success', title: `Bid placed · you’re ${result.rank_label}`, description })
      void queryClient.invalidateQueries({ queryKey: queryKeys.rfq(rfq.id) })
      void queryClient.invalidateQueries({ queryKey: queryKeys.activity(rfq.id) })
    },
    onError: (error) => {
      if (error instanceof ApiError) {
        const fields = bidServerErrors(error)
        setFromServer(fields)
        const first = BID_FIELD_ORDER.find((field) => field in fields)
        if (first) focus(first)
        else setBanner(errorMessage(error))
        if (error.code === 'AUCTION_CLOSED' || error.code === 'AUCTION_NOT_STARTED') {
          void queryClient.invalidateQueries({ queryKey: queryKeys.rfq(rfq.id) })
        }
      } else {
        setBanner(errorMessage(error))
      }
    },
  })

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    setSubmitted(true)
    setBanner(null)
    const first = BID_FIELD_ORDER.find((field) => field in errors)
    if (first) {
      focus(first)
      return
    }
    setFromServer({})
    submit.mutate()
  }

  if (rfq.status === 'SCHEDULED') {
    return (
      <Card title="Place a bid">
        <p className="text-sm text-ink-2">
          Bidding opens at <DateTime value={rfq.bid_start_at} className="text-ink" />.
        </p>
      </Card>
    )
  }

  const moneyField = (field: 'freight' | 'origin' | 'destination', label: string) => (
    <Field id={bidFieldId(field)} label={label} error={shown(field)}>
      {(control) => (
        <div className="relative">
          <span aria-hidden className="pointer-events-none absolute inset-y-0 left-3 flex items-center font-mono text-sm text-ink-3">
            ₹
          </span>
          <input
            {...control}
            inputMode="decimal"
            value={values[field]}
            onChange={(event) => set(field, event.target.value)}
            onBlur={touch(field)}
            disabled={!open}
            className={cx(inputClasses, 'pl-7 font-mono tabular-nums')}
          />
        </div>
      )}
    </Field>
  )

  return (
    <Card title="Place a bid">
      <form noValidate onSubmit={onSubmit} aria-label="Place a bid" className="space-y-4">
        {!open && (
          <p role="status" className="rounded-lg border border-line bg-white/[0.03] px-3 py-2.5 text-sm text-ink-2">
            {rfq.status === 'ACTIVE' ? 'Closing… waiting for the final result.' : 'Bidding has closed for this auction.'}
          </p>
        )}
        {open && countdown.isInWindow && (
          <p role="status" className="rounded-lg border border-amber/40 bg-amber/10 px-3 py-2.5 text-[13px] text-amber-2">
            You’re inside the trigger window. {QUALIFYING[config.trigger_type]} extends the close by{' '}
            {config.extension_duration_minutes} min.
          </p>
        )}
        {previous && (
          <p className="text-[13px] text-ink-2">
            Your current bid <Money amount={previous.total_amount} className="text-ink" /> ({previous.rank_label}). A new
            bid must be lower.
          </p>
        )}
        {banner && (
          <p role="alert" className="rounded-lg border border-danger/40 bg-danger/10 px-3 py-2.5 text-sm text-ink">
            {banner}
          </p>
        )}

        <Field id={bidFieldId('carrierName')} label="Carrier" error={shown('carrierName')}>
          {(control) => (
            <input
              {...control}
              value={values.carrierName}
              onChange={(event) => set('carrierName', event.target.value)}
              onBlur={touch('carrierName')}
              placeholder="e.g. Swift Ocean Line"
              maxLength={100}
              disabled={!open}
              className={inputClasses}
            />
          )}
        </Field>
        <div className="grid grid-cols-3 gap-2.5">
          {moneyField('freight', 'Freight')}
          {moneyField('origin', 'Origin')}
          {moneyField('destination', 'Destination')}
        </div>
        <div
          className={cx(
            'flex items-baseline justify-between rounded-lg border px-3 py-2.5',
            shown('total') ? 'border-danger/50' : 'border-line',
          )}
        >
          <span className="text-xs text-ink-3">Total</span>
          <span className="font-mono text-lg text-ink tabular-nums">
            {total !== null ? <Money amount={centsToAmount(total)} className="text-ink" /> : '—'}
          </span>
        </div>
        {shown('total') && (
          <p id={bidFieldId('total')} role="alert" className="-mt-2 text-xs text-danger">
            {shown('total')}
          </p>
        )}
        <div className="grid grid-cols-2 gap-2.5">
          <Field id={bidFieldId('transitDays')} label="Transit time" error={shown('transitDays')}>
            {(control) => (
              <UnitInput
                control={control}
                unit="days"
                min={1}
                max={365}
                value={values.transitDays}
                onChange={(value) => set('transitDays', value)}
                onBlur={touch('transitDays')}
                disabled={!open}
              />
            )}
          </Field>
          <Field id={bidFieldId('validityDate')} label="Quote valid until" error={shown('validityDate')}>
            {(control) => (
              <input
                {...control}
                type="date"
                min={rfq.pickup_date}
                value={values.validityDate}
                onChange={(event) => set('validityDate', event.target.value)}
                onBlur={touch('validityDate')}
                disabled={!open}
                className={inputClasses}
              />
            )}
          </Field>
        </div>
        <Field id={bidFieldId('notes')} label="Notes" optional error={shown('notes')}>
          {(control) => (
            <textarea
              {...control}
              value={values.notes}
              onChange={(event) => set('notes', event.target.value)}
              onBlur={touch('notes')}
              rows={2}
              maxLength={500}
              disabled={!open}
              placeholder="e.g. Includes BAF"
              className={cx(inputClasses, 'h-auto py-2')}
            />
          )}
        </Field>
        <Button type="submit" className="w-full" disabled={!open || submit.isPending}>
          {submit.isPending ? 'Placing bid…' : previous ? 'Place a lower bid' : 'Place bid'}
        </Button>
      </form>
    </Card>
  )
}

