type Props = { data: Record<string, number> }

export default function AccountOverview({ data }: Props) {
  const cards = [
    { key: 'follower_count', label: 'Followers' },
    { key: 'reach', label: 'Accounts reached' },
    { key: 'accounts_engaged', label: 'Accounts engaged' },
  ]
  return (
    <div style={{ display: 'flex', gap: '1rem', flexWrap: 'wrap' }}>
      {cards.map(({ key, label }) => (
        <div
          key={key}
          style={{
            padding: '1rem 1.25rem',
            background: '#18181b',
            borderRadius: 10,
            minWidth: 140,
          }}
        >
          <div style={{ fontSize: '0.875rem', color: '#a1a1aa', marginBottom: 4 }}>{label}</div>
          <div style={{ fontSize: '1.5rem', fontWeight: 700 }}>
            {data[key] != null ? Number(data[key]).toLocaleString() : '—'}
          </div>
        </div>
      ))}
    </div>
  )
}
