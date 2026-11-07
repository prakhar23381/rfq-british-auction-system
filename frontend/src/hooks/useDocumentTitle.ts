import { useEffect } from 'react'

const APP_NAME = 'British Auction RFQ'

export function useDocumentTitle(title: string | null | undefined): void {
  useEffect(() => {
    document.title = title ? `${title} · ${APP_NAME}` : APP_NAME
  }, [title])
}
