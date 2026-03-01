type Props = { data: Record<string, number> }

const LABELS: Record<string, string> = {
  views: 'Views',
  reach: 'Reach',
  saved: 'Saves',
  shares: 'Shares',
  total_interactions: 'Total interactions',
  ig_reels_avg_watch_time: 'Avg watch time (s)',
}

export default function ReelInsights({ data }: Props) {
  const entries = Object.entries(data).filter(([, v]) => v != null)
  return (
    <div style={{ display: 'flex', flexDirection: 'column', gap: '0.75rem' }}>
      {entries.map(([key, value]) => (
        <div
          key={key}
          style={{
            display: 'flex',
            justifyContent: 'space-between',
            alignItems: 'center',
            padding: '1rem 1.25rem',
            background: '#18181b',
            borderRadius: 10,
          }}
        >
          <span style={{ color: '#a1a1aa' }}>{LABELS[key] ?? key}</span>
          <span style={{ fontWeight: 600 }}>
            {typeof value === 'number' && key.includes('watch_time') ? `${value}s` : value.toLocaleString()}
          </span>
        </div>
      ))}
      {entries.length === 0 && <p style={{ color: '#a1a1aa' }}>No insights available for this reel.</p>}
    </div>
  )
}
