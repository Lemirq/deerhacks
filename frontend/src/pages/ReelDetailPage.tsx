import { useAuth0 } from '@auth0/auth0-react'
import { useEffect, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { useInstagramApi } from '../hooks/useInstagramApi'
import ReelInsights from '../components/ReelInsights'

export default function ReelDetailPage() {
  const { mediaId } = useParams<{ mediaId: string }>()
  const { logout } = useAuth0()
  const { fetchReelInsights } = useInstagramApi()
  const [insights, setInsights] = useState<Record<string, number> | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    if (!mediaId) return
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchReelInsights(mediaId)
      .then((data) => {
        if (!cancelled) setInsights(data as Record<string, number>)
      })
      .catch((e) => !cancelled && setError(e.message))
      .finally(() => !cancelled && setLoading(false))
    return () => { cancelled = true }
  }, [mediaId, fetchReelInsights])

  return (
    <div style={{ padding: '1rem', maxWidth: 700, margin: '0 auto' }}>
      <header style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '1.5rem' }}>
        <nav style={{ display: 'flex', gap: '1rem' }}>
          <Link to="/dashboard">Dashboard</Link>
          <Link to="/reels">Reels</Link>
        </nav>
        <button
          onClick={() => logout({ logoutParams: { returnTo: window.location.origin } })}
          style={{ padding: '0.5rem 1rem', borderRadius: 6, border: 'none', background: '#3f3f46', color: '#e4e4e7' }}
        >
          Log out
        </button>
      </header>
      <h1 style={{ margin: '0 0 1rem' }}>Reel insights</h1>
      {loading && <p>Loading...</p>}
      {error && <p style={{ color: '#f87171' }}>{error}</p>}
      {!loading && !error && insights && <ReelInsights data={insights} />}
    </div>
  )
}
