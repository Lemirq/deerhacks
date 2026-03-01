import { Link } from 'react-router-dom'

type Reel = {
  id: string
  caption?: string
  media_url?: string
  thumbnail_url?: string
  timestamp?: string
  like_count?: number
  comments_count?: number
}

export default function ReelCard({ reel }: { reel: Reel }) {
  const thumb = reel.thumbnail_url || reel.media_url
  return (
    <Link
      to={`/reels/${reel.id}`}
      style={{
        display: 'block',
        background: '#18181b',
        borderRadius: 10,
        overflow: 'hidden',
        color: 'inherit',
        textDecoration: 'none',
      }}
    >
      {thumb && (
        <div style={{ aspectRatio: '9/16', background: '#27272a' }}>
          <img
            src={thumb}
            alt=""
            style={{ width: '100%', height: '100%', objectFit: 'cover' }}
          />
        </div>
      )}
      <div style={{ padding: '0.75rem' }}>
        <div style={{ fontSize: '0.875rem', color: '#a1a1aa' }}>
          {reel.like_count != null && `${reel.like_count} likes`}
          {reel.like_count != null && reel.comments_count != null && ' · '}
          {reel.comments_count != null && `${reel.comments_count} comments`}
        </div>
        {reel.caption && (
          <p style={{ margin: '0.25rem 0 0', fontSize: '0.8rem', overflow: 'hidden', textOverflow: 'ellipsis', whiteSpace: 'nowrap' }}>
            {reel.caption}
          </p>
        )}
      </div>
    </Link>
  )
}
