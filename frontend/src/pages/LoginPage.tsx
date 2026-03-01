import { useAuth0 } from '@auth0/auth0-react'

export default function LoginPage() {
  const { loginWithRedirect, isAuthenticated, isLoading } = useAuth0()

  if (isLoading) return <div className="loading">Loading...</div>
  if (isAuthenticated) {
    window.location.href = '/dashboard'
    return null
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: '1.25rem', padding: '1rem' }}>
      <h1 style={{ margin: 0, fontSize: '1.75rem' }}>Neuro-Sync</h1>
      <p style={{ color: '#a1a1aa', margin: 0 }}>Creator analytics — sign in to continue</p>
      <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem', width: '100%', maxWidth: 280 }}>
        <button
          onClick={() => loginWithRedirect({ authorizationParams: { connection: 'google-oauth2' } })}
          style={{
            padding: '0.75rem 1.5rem',
            fontSize: '1rem',
            fontWeight: 600,
            borderRadius: 8,
            border: 'none',
            background: '#4285f4',
            color: '#fff',
          }}
        >
          Log in with Google
        </button>
        <button
          onClick={() => loginWithRedirect({ authorizationParams: { connection: 'instagram' } })}
          style={{
            padding: '0.75rem 1.5rem',
            fontSize: '1rem',
            fontWeight: 600,
            borderRadius: 8,
            border: 'none',
            background: '#a78bfa',
            color: '#0f0f12',
          }}
        >
          Log in with Instagram
        </button>
      </div>
    </div>
  )
}
