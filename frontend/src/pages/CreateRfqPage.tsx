import { useMutation, useQueryClient } from '@tanstack/react-query'
import { type FormEvent, useMemo, useState } from 'react'
import { useNavigate } from 'react-router'

import { ApiError } from '../api/client'
import { api, queryKeys } from '../api/endpoints'
import { errorMessage } from '../api/errors'
import { Field, LockedSwitch, UnitInput } from '../components/form/fields'
import { inputClasses } from '../components/form/inputClasses'
import { Button, ButtonLink } from '../components/ui/Button'
import { Card } from '../components/ui/Card'
import { Accent, PageHeader } from '../components/ui/PageHeader'
import { useToast } from '../components/ui/toastContext'
import {
  defaultValues,
  FIELD_ORDER,
  type FieldName,
  fieldId,
  type FormErrors,
  parseTimes,
  type RfqFormValues,
  serverErrors,
  shiftSchedule,
  toPayload,
  validate,
} from '../features/createRfq/form'
import { SchedulePreview } from '../features/createRfq/SchedulePreview'
import { TriggerTypeCards } from '../features/createRfq/TriggerTypeCards'
import { useDocumentTitle } from '../hooks/useDocumentTitle'
import { ceilToMinute, localTimeZone, MINUTE } from '../lib/datetimeLocal'
import { serverNow } from '../lib/serverClock'

/** Wrapped in <RequireRole role="BUYER"> by the router (R1–R5). */
export function CreateRfqPage() {
  useDocumentTitle('Create RFQ')
  const navigate = useNavigate()
  const queryClient = useQueryClient()
  const toast = useToast()

  const [values, setValues] = useState<RfqFormValues>(() => defaultValues(serverNow()))
  const [touched, setTouched] = useState<ReadonlySet<FieldName>>(() => new Set())
  const [submitted, setSubmitted] = useState(false)
  const [fromServer, setFromServer] = useState<FormErrors>({})
  const [banner, setBanner] = useState<string | null>(null)

  const errors = validate(values, serverNow())
  const times = useMemo(() => parseTimes(values), [values])
  const zone = useMemo(() => localTimeZone(), [])

  const shown = (field: FieldName): string | undefined =>
    fromServer[field] ?? (submitted || touched.has(field) ? errors[field] : undefined)

  const set = <K extends FieldName>(field: K, value: RfqFormValues[K]) => {
    setValues((current) => ({ ...current, [field]: value }))
    setFromServer((current) => {
      if (!(field in current)) return current
      const next = { ...current }
      delete next[field]
      return next
    })
  }
  const touch = (field: FieldName) => () =>
    setTouched((current) => (current.has(field) ? current : new Set(current).add(field)))

  const focusField = (field: FieldName) => {
    const element =
      document.getElementById(fieldId(field)) ?? document.querySelector<HTMLElement>(`[name="${field}"]`)
    element?.focus()
  }

  const create = useMutation({
    mutationFn: api.createRfq,
    onSuccess: (detail) => {
      void queryClient.invalidateQueries({ queryKey: queryKeys.rfqLists })
      queryClient.setQueryData(queryKeys.rfq(detail.rfq.id), detail)
      toast.show({
        tone: 'success',
        title: 'RFQ created',
        description: `${detail.rfq.reference_id} · ${detail.rfq.name}`,
      })
      navigate(`/rfqs/${detail.rfq.id}`)
    },
    onError: (error) => {
      if (!(error instanceof ApiError)) {
        setBanner(errorMessage(error))
        return
      }
      const { fields, other } = serverErrors(error)
      setFromServer(fields)
      const hasFields = Object.keys(fields).length > 0
      setBanner(other ?? (hasFields ? null : errorMessage(error)))
      const first = FIELD_ORDER.find((field) => field in fields)
      if (first) focusField(first)
    },
  })

  const onSubmit = (event: FormEvent) => {
    event.preventDefault()
    setSubmitted(true)
    setBanner(null)
    const current = validate(values, serverNow())
    const first = FIELD_ORDER.find((field) => field in current)
    if (first) {
      focusField(first)
      return
    }
    setFromServer({})
    create.mutate(toPayload(values))
  }

  const startInPast = errors.bidStartAt === 'Bid start can’t be in the past.'

  return (
    <>
      <PageHeader
        eyebrow="New RFQ"
        title={
          <>
            Create a British <Accent>auction</Accent>
          </>
        }
        description="Set the bidding schedule and how late bids extend the auction. Suppliers see it the moment you create it."
      />

      <form noValidate onSubmit={onSubmit} className="grid gap-6 lg:grid-cols-[minmax(0,1fr)_340px] lg:items-start">
        <div className="space-y-6">
          {banner && (
            <div role="alert" className="rounded-xl border border-danger/40 bg-danger/10 px-4 py-3 text-sm text-ink">
              {banner}
            </div>
          )}

          <Card title="RFQ details">
            <div className="grid gap-5 sm:grid-cols-2">
              <Field id={fieldId('name')} label="RFQ name" error={shown('name')} className="sm:col-span-2">
                {(control) => (
                  <input
                    {...control}
                    value={values.name}
                    onChange={(event) => set('name', event.target.value)}
                    onBlur={touch('name')}
                    placeholder="e.g. Mumbai to Rotterdam, 2 x 40HC"
                    maxLength={120}
                    autoComplete="off"
                    className={inputClasses}
                  />
                )}
              </Field>
              <Field
                id={fieldId('referenceId')}
                label="Reference ID"
                optional
                hint="Leave blank to generate one (RFQ-YYYY-NNNN)."
                error={shown('referenceId')}
              >
                {(control) => (
                  <input
                    {...control}
                    value={values.referenceId}
                    onChange={(event) => set('referenceId', event.target.value.toUpperCase())}
                    onBlur={touch('referenceId')}
                    placeholder="Auto"
                    maxLength={30}
                    autoComplete="off"
                    spellCheck={false}
                    className={`${inputClasses} font-mono uppercase placeholder:normal-case`}
                  />
                )}
              </Field>
              <Field
                id={fieldId('pickupDate')}
                label="Pickup / service date"
                hint="On or after the bid close date."
                error={shown('pickupDate')}
              >
                {(control) => (
                  <input
                    {...control}
                    type="date"
                    value={values.pickupDate}
                    onChange={(event) => set('pickupDate', event.target.value)}
                    onBlur={touch('pickupDate')}
                    className={inputClasses}
                  />
                )}
              </Field>
            </div>
          </Card>

          <Card
            title="Bidding schedule"
            actions={
              <span className="font-mono text-[11px] text-ink-3" title={zone.id}>
                Your time zone · {zone.abbreviation}
              </span>
            }
          >
            <div className="grid gap-5 md:grid-cols-3">
              <Field id={fieldId('bidStartAt')} label="Bid start" hint="Bidding opens." error={shown('bidStartAt')}>
                {(control) => (
                  <input
                    {...control}
                    type="datetime-local"
                    value={values.bidStartAt}
                    onChange={(event) => set('bidStartAt', event.target.value)}
                    onBlur={touch('bidStartAt')}
                    className={inputClasses}
                  />
                )}
              </Field>
              <Field id={fieldId('bidCloseAt')} label="Bid close" hint="Late bids can extend it." error={shown('bidCloseAt')}>
                {(control) => (
                  <input
                    {...control}
                    type="datetime-local"
                    value={values.bidCloseAt}
                    onChange={(event) => set('bidCloseAt', event.target.value)}
                    onBlur={touch('bidCloseAt')}
                    className={inputClasses}
                  />
                )}
              </Field>
              <Field
                id={fieldId('forcedCloseAt')}
                label="Forced bid close"
                hint="Hard stop. Extensions never pass it."
                error={shown('forcedCloseAt')}
              >
                {(control) => (
                  <input
                    {...control}
                    type="datetime-local"
                    value={values.forcedCloseAt}
                    onChange={(event) => set('forcedCloseAt', event.target.value)}
                    onBlur={touch('forcedCloseAt')}
                    className={inputClasses}
                  />
                )}
              </Field>
            </div>
            {startInPast && shown('bidStartAt') && (
              <button
                type="button"
                onClick={() => setValues((current) => shiftSchedule(current, ceilToMinute(serverNow() + 2 * MINUTE)))}
                className="mt-3 text-xs text-peri-2 underline-offset-4 hover:underline"
              >
                Move the schedule to start in 2 minutes
              </button>
            )}
          </Card>

          <Card title="British auction">
            <div className="space-y-6">
              <LockedSwitch
                id="rfq-british"
                label="British auction (reverse)"
                description="Always on: suppliers bid the price down, and late bids can extend the close."
              />
              <div className="grid gap-5 sm:grid-cols-2">
                <Field
                  id={fieldId('triggerWindowMinutes')}
                  label="Trigger window (X)"
                  hint="How long before the close bids are watched."
                  error={shown('triggerWindowMinutes')}
                >
                  {(control) => (
                    <UnitInput
                      control={control}
                      unit="min"
                      min={1}
                      max={120}
                      value={values.triggerWindowMinutes}
                      onChange={(value) => set('triggerWindowMinutes', value)}
                      onBlur={touch('triggerWindowMinutes')}
                    />
                  )}
                </Field>
                <Field
                  id={fieldId('extensionDurationMinutes')}
                  label="Extension duration (Y)"
                  hint="Time added to the close when triggered."
                  error={shown('extensionDurationMinutes')}
                >
                  {(control) => (
                    <UnitInput
                      control={control}
                      unit="min"
                      min={1}
                      max={120}
                      value={values.extensionDurationMinutes}
                      onChange={(value) => set('extensionDurationMinutes', value)}
                      onBlur={touch('extensionDurationMinutes')}
                    />
                  )}
                </Field>
              </div>
              <TriggerTypeCards
                value={values.triggerType}
                onChange={(value) => set('triggerType', value)}
                times={times}
                error={shown('triggerType')}
              />
            </div>
          </Card>
        </div>

        <div className="space-y-4 lg:sticky lg:top-24">
          <Card title="How it will run">
            <SchedulePreview times={times} triggerType={values.triggerType} />
          </Card>
          <div className="flex flex-col gap-2">
            <Button type="submit" disabled={create.isPending}>
              {create.isPending ? 'Creating…' : 'Create RFQ'}
            </Button>
            <ButtonLink to="/" variant="ghost">
              Cancel
            </ButtonLink>
          </div>
        </div>
      </form>
    </>
  )
}
