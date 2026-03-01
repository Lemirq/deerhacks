import { StrictMode } from 'react'
import { createRoot } from 'react-dom/client'
import { Auth0Provider } from '@auth0/auth0-react'
import App from './App'
import './index.css'

const domain = import.meta.env.VITE_AUTH0_DOMAIN
const clientId = import.meta.env.VITE_AUTH0_CLIENT_ID
const audience = import.meta.env.VITE_AUTH0_AUDIENCE

if (!domain || !clientId) {
  console.warn('Missing VITE_AUTH0_DOMAIN or VITE_AUTH0_CLIENT_ID. Copy .env.example to .env and set values from Auth0.')
}

createRoot(document.getElementById('root')!).render(
  <StrictMode>
    <Auth0Provider
      domain={domain || ''}
      clientId={clientId || ''}
      authorizationParams={{
        redirect_uri: window.location.origin,
        audience: audience || undefined,
      }}
    >
      <App />
    </Auth0Provider>
  </StrictMode>,
)
