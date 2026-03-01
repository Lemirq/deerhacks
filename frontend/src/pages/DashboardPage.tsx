import { useAuth0 } from '@auth0/auth0-react'
import { useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { useInstagramApi } from '../hooks/useInstagramApi'
import AccountOverview from '../components/AccountOverview'
import FollowerGrowth from '../components/FollowerGrowth'

export default function DashboardPage() {
  const { logout } = useAuth0()
  const { fetchAccountOverview, fetchFollowerGrowth } = useInstagramApi()
  const [overview, setOverview] = useState<Record<string, number> | null>(null)
  const [growth, setGrowth] = useState<{ date: string; value: number }[] | null>(null)
  const [error, setError] = useState<string | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    setError(null)
    Promise.all([fetchAccountOverview(), fetchFollowerGrowth(30)])
      .then(([ov, gr]) => {
        if (!cancelled) {
          setOverview(ov as Record<string, number>)
          setGrowth(gr as { date: string; value: number }[])
        }
      })
      .catch((e) => !cancelled && setError(e.message))
      .finally(() => !cancelled && setLoading(false))
    return () => { cancelled = true }
  }, [fetchAccountOverview, fetchFollowerGrowth])

  return (
    <div style={{ padding: '1rem', maxWidth: 900, margin: '0 auto' }}>
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
      <h1 style={{ margin: '0 0 1rem' }}>Account overview</h1>
      {loading && <p>Loading...</p>}
      {error && <p style={{ color: '#f87171' }}>{error}</p>}
      {!loading && !error && overview && <AccountOverview data={overview} />}
      {!loading && !error && growth && growth.length > 0 && (
        <>
          <h2 style={{ margin: '1.5rem 0 0.75rem' }}>Follower growth</h2>
          <FollowerGrowth data={growth} />
        </>
      )}
    </div>
  )
}
