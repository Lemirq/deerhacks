import { useAuth0 } from '@auth0/auth0-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useInstagramApi } from '../hooks/useInstagramApi'
import ReelCard from '../components/ReelCard'

type Reel = {
  id: string
  caption?: string
  media_url?: string
  thumbnail_url?: string
  timestamp?: string
  like_count?: number
  comments_count?: number
  permalink?: string
}

export default function ReelsPage() {
  const { logout } = useAuth0()
  const { fetchReels } = useInstagramApi()
  const [reels, setReels] = useState<Reel[]>([])
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    fetchReels()
      .then((data: { data?: Reel[] }) => {
        if (!cancelled) setReels(Array.isArray(data?.data) ? data.data : data ? [data] : [])
      })
      .catch((e) => !cancelled && setError(e.message))
      .finally(() => !cancelled && setLoading(false))
    return () => { cancelled = true }
  }, [fetchReels])

  return (
    <div style={{ padding: '1rem', maxWidth: 1000, margin: '0 auto' }}>
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
      <h1 style={{ margin: '0 0 1rem' }}>Your reels</h1>
      {loading && <p>Loading...</p>}
      {error && <p style={{ color: '#f87171' }}>{error}</p>}
      {!loading && !error && (
        <div style={{ display: 'grid', gridTemplateColumns: 'repeat(auto-fill, minmax(200px, 1fr))', gap: '1rem' }}>
          {reels.map((reel) => (
            <ReelCard key={reel.id} reel={reel} />
          ))}
          {reels.length === 0 && <p style={{ color: '#a1a1aa' }}>No reels found.</p>}
        </div>
      )}
    </div>
  )
}
