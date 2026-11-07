import { Button } from './Button'

interface PaginationProps {
  page: number
  pageSize: number
  total: number
  onChange: (page: number) => void
}

export function Pagination({ page, pageSize, total, onChange }: PaginationProps) {
  const pages = Math.max(1, Math.ceil(total / pageSize))
  if (total <= pageSize && page === 1) return null
  const first = Math.min(total, (page - 1) * pageSize + 1)
  const last = Math.min(total, page * pageSize)
  return (
    <nav aria-label="Pagination" className="flex items-center justify-between gap-3 px-1 pt-4">
      <p className="font-mono text-xs text-ink-3">
        {first}–{last} of {total}
      </p>
      <div className="flex gap-2">
        <Button variant="subtle" size="sm" disabled={page <= 1} onClick={() => onChange(page - 1)}>
          ← Previous
        </Button>
        <Button variant="subtle" size="sm" disabled={page >= pages} onClick={() => onChange(page + 1)}>
          Next →
        </Button>
      </div>
    </nav>
  )
}
