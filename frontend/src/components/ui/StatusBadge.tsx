import type { AuctionStatus } from '../../api/types'
import { STATUS_LABELS } from '../../lib/format'
import { Chip, type ChipTone } from './Chip'

const TONE: Record<AuctionStatus, ChipTone> = {
  SCHEDULED: 'lilac',
  ACTIVE: 'mint',
  CLOSED: 'peri',
  FORCE_CLOSED: 'rose',
}

export function StatusBadge({ status }: { status: AuctionStatus }) {
  return (
    <Chip tone={TONE[status]} dot={status === 'ACTIVE' ? 'pulse' : true}>
      {STATUS_LABELS[status]}
    </Chip>
  )
}
