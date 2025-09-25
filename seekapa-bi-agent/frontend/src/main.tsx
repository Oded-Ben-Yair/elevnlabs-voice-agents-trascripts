import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { initializeWebVitalsTracking } from './utils/webVitals'
import './index.css'
import App from './App.tsx'

// Initialize performance tracking
initializeWebVitalsTracking()

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <App />
  </StrictMode>,
)

// Register service worker for PWA
if ('serviceWorker' in navigator && import.meta.env.PROD) {
  window.addEventListener('load', () => {
    navigator.serviceWorker.register('/sw.js')
      .then((registration) => {
        console.log('SW registered: ', registration)
      })
      .catch((registrationError) => {
        console.log('SW registration failed: ', registrationError)
      })
  })
}
