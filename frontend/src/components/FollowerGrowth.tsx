import { LineChart, Line, XAxis, YAxis, Tooltip, ResponsiveContainer } from 'recharts'

type Props = { data: { date: string; value: number }[] }

export default function FollowerGrowth({ data }: Props) {
  return (
    <div style={{ height: 260, background: '#18181b', borderRadius: 10, padding: '1rem' }}>
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={data}>
          <XAxis dataKey="date" stroke="#71717a" fontSize={12} />
          <YAxis stroke="#71717a" fontSize={12} tickFormatter={(v) => v.toLocaleString()} />
          <Tooltip
            contentStyle={{ background: '#27272a', border: 'none', borderRadius: 8 }}
            formatter={(value: number) => [value.toLocaleString(), 'Followers']}
            labelFormatter={(label) => `Date: ${label}`}
          />
          <Line type="monotone" dataKey="value" stroke="#a78bfa" strokeWidth={2} dot={false} />
        </LineChart>
      </ResponsiveContainer>
    </div>
  )
}
