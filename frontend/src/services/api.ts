const API_BASE = '/api/instagram'

export async function fetchWithAuth(url: string, token: string, options?: RequestInit) {
  const res = await fetch(`${API_BASE}${url}`, {
    ...options,
    headers: {
      Authorization: `Bearer ${token}`,
      'Content-Type': 'application/json',
      ...options?.headers,
    },
  })
  if (!res.ok) {
    const err = await res.json().catch(() => ({ message: res.statusText }))
    throw new Error((err as { message?: string }).message || res.statusText)
  }
  return res.json()
}

export const api = {
  accountOverview: (token: string) => fetchWithAuth('/account/overview', token),
  followerGrowth: (token: string, days = 30) =>
    fetchWithAuth(`/account/follower-growth?days=${days}`, token),
  reels: (token: string) => fetchWithAuth('/reels', token),
  reelInsights: (token: string, mediaId: string) =>
    fetchWithAuth(`/reels/${encodeURIComponent(mediaId)}/insights`, token),
}
