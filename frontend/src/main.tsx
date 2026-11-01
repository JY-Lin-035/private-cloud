import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import './index.css'
import App from './App.tsx'
import { registerMediaSW } from './utils/mediaCache'
import { setAuthedUI } from './utils/authedUI'
import { authApi } from './api/authApi'

void registerMediaSW()
authApi.checkSession()
  .then(s => setAuthedUI(!!s?.authenticated))
  .catch(() => setAuthedUI(false))

createRoot(document.getElementById('app')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)
