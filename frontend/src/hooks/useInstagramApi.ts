import { useAuth0 } from '@auth0/auth0-react'
import { useCallback } from 'react'
import { api } from '../services/api'

export function useInstagramApi() {
  const { getAccessTokenSilently } = useAuth0()

  const getToken = useCallback(async () => {
    try {
      return await getAccessTokenSilently()
    } catch (e) {
      console.error('Failed to get access token', e)
      return null
    }
  }, [getAccessTokenSilently])

  const fetchAccountOverview = useCallback(async () => {
    const token = await getToken()
    if (!token) throw new Error('Not authenticated')
    return api.accountOverview(token)
  }, [getToken])

  const fetchFollowerGrowth = useCallback(async (days = 30) => {
    const token = await getToken()
    if (!token) throw new Error('Not authenticated')
    return api.followerGrowth(token, days)
  }, [getToken])

  const fetchReels = useCallback(async () => {
    const token = await getToken()
    if (!token) throw new Error('Not authenticated')
    return api.reels(token)
  }, [getToken])

  const fetchReelInsights = useCallback(async (mediaId: string) => {
    const token = await getToken()
    if (!token) throw new Error('Not authenticated')
    return api.reelInsights(token, mediaId)
  }, [getToken])

  return {
    fetchAccountOverview,
    fetchFollowerGrowth,
    fetchReels,
    fetchReelInsights,
  }
}
