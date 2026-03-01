import { useAuth0 } from '@auth0/auth0-react'

export default function LoginPage() {
  const { loginWithRedirect, isAuthenticated, isLoading } = useAuth0()

  if (isLoading) return <div className="loading">Loading...</div>
  if (isAuthenticated) {
    window.location.href = '/dashboard'
    return null
  }

  return (
    <div style={{ minHeight: '100vh', display: 'flex', alignItems: 'center', justifyContent: 'center', flexDirection: 'column', gap: '1rem', padding: '1rem' }}>
      <h1 style={{ margin: 0, fontSize: '1.75rem' }}>Neuro-Sync</h1>
      <p style={{ color: '#a1a1aa', margin: 0 }}>Creator analytics — sign in to continue</p>
      <button
        onClick={() => loginWithRedirect()}
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
        Log in
      </button>
    </div>
  )
}
