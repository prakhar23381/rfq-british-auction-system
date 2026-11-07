import { cx } from '../ui/cx'

export const inputClasses = cx(
  'h-10 w-full min-w-0 rounded-lg border border-[rgb(190_170_255/0.14)] bg-[rgb(170_150_255/0.06)] px-3 text-sm text-ink',
  'placeholder:text-ink-3 outline-none transition-colors [color-scheme:dark]',
  'hover:border-[rgb(190_170_255/0.26)] focus:border-peri-2 focus:bg-[rgb(170_150_255/0.1)]',
  'aria-[invalid=true]:border-danger/70 aria-[invalid=true]:focus:border-danger',
)
