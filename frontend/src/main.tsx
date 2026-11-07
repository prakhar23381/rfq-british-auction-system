import '@fontsource-variable/inter-tight'
import '@fontsource/fira-code/400.css'
import '@fontsource/fira-code/500.css'
import '@fontsource/instrument-serif/400-italic.css'
import './index.css'

import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { BrowserRouter } from 'react-router'

import { App } from './App'
import { Providers } from './providers'
import { createQueryClient } from './queryClient'

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <BrowserRouter>
      <Providers client={createQueryClient()}>
        <App />
      </Providers>
    </BrowserRouter>
  </StrictMode>,
)
