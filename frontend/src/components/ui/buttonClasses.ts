import { cx } from './cx'

export type ButtonVariant = 'primary' | 'ghost' | 'subtle' | 'danger'
export type ButtonSize = 'sm' | 'md'

const VARIANTS: Record<ButtonVariant, string> = {
  primary:
    'bg-peri text-white shadow-[0_8px_26px_rgb(90_96_255/0.35)] hover:bg-peri-2 hover:shadow-[0_10px_34px_rgb(110_116_255/0.5)]',
  ghost: 'border border-[rgb(230_226_255/0.42)] bg-white/[0.03] text-ink hover:bg-white/10',
  subtle: 'border border-line bg-violet/10 text-ink-2 hover:bg-violet/20 hover:text-ink',
  danger: 'border border-danger/40 bg-danger/10 text-danger hover:bg-danger/20',
}

const SIZES: Record<ButtonSize, string> = {
  sm: 'h-8 gap-1.5 rounded-lg px-3 text-xs',
  md: 'h-11 gap-2 rounded-[11px] px-[18px] text-[15px]',
}

export function buttonClasses(
  variant: ButtonVariant = 'primary',
  size: ButtonSize = 'md',
  className?: string,
): string {
  return cx(
    'inline-flex shrink-0 items-center justify-center font-medium whitespace-nowrap',
    'transition-[transform,background-color,box-shadow,color] duration-300',
    'hover:-translate-y-px disabled:pointer-events-none disabled:opacity-50',
    VARIANTS[variant],
    SIZES[size],
    className,
  )
}
