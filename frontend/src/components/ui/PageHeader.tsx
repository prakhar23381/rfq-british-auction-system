import type { ReactNode } from 'react'

import { Eyebrow } from './Card'

interface PageHeaderProps {
  eyebrow?: string
  title: ReactNode
  description?: ReactNode
  actions?: ReactNode
}

export function PageHeader({ eyebrow, title, description, actions }: PageHeaderProps) {
  return (
    <div className="mb-8 flex flex-wrap items-end gap-x-6 gap-y-4">
      <div className="min-w-0 flex-1">
        {eyebrow && <Eyebrow className="mb-3">{eyebrow}</Eyebrow>}
        <h1 className="text-[32px] leading-[1.1] font-light tracking-[-0.028em] text-ink sm:text-[40px]">
          {title}
        </h1>
        {description && <p className="mt-3 max-w-2xl text-[15px] leading-relaxed text-ink-2">{description}</p>}
      </div>
      {actions && <div className="flex flex-wrap gap-2">{actions}</div>}
    </div>
  )
}

/** One accent word in a heading, in Instrument Serif italic. */
export function Accent({ children }: { children: ReactNode }) {
  return <em className="font-serif font-normal tracking-normal text-peri-2">{children}</em>
}
