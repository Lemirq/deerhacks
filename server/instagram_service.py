"""
Instagram Graph API client for media list, media insights, and user insights.
Uses the Instagram access token obtained from Auth0 (user's identity).
"""
import httpx

GRAPH_BASE = "https://graph.instagram.com/v22.0"


def _get(path: str, params: dict, access_token: str) -> dict:
    params = {**params, "access_token": access_token}
    with httpx.Client() as client:
        r = client.get(f"{GRAPH_BASE}{path}", params=params)
        if r.status_code != 200:
            err = r.json() if r.headers.get("content-type", "").startswith("application/json") else {}
            msg = err.get("error", {}).get("message", r.text) or str(r.status_code)
            raise ValueError(msg)
        return r.json()


def get_me_media(access_token: str, limit: int = 25) -> dict:
    """List user's media (reels/posts). Filter to reels in the route."""
    fields = "id,caption,media_type,media_url,thumbnail_url,timestamp,permalink,like_count,comments_count"
    return _get("/me/media", {"fields": fields, "limit": limit}, access_token)


def get_media_insights(media_id: str, access_token: str) -> dict:
    """Reel insights: views, reach, saved, shares, total_interactions, ig_reels_avg_watch_time."""
    metrics = "views,reach,saved,shares,total_interactions,ig_reels_avg_watch_time"
    data = _get(f"/{media_id}/insights", {"metric": metrics}, access_token)
    # API returns { "data": [ {"name": "views", "values": [{"value": 123}] }, ... ] }
    out = {}
    for item in data.get("data") or []:
        name = item.get("name")
        values = item.get("values") or []
        if name and values and isinstance(values[0].get("value"), (int, float)):
            out[name] = int(values[0]["value"])
    return out


def get_user_insights(access_token: str, metric: str, period: str = "day", since: str | None = None, until: str | None = None) -> dict:
    """User-level insights: reach, accounts_engaged, follower_count."""
    params = {"metric": metric, "period": period}
    if since:
        params["since"] = since
    if until:
        params["until"] = until
    data = _get("/me/insights", params, access_token)
    return data


def get_account_overview(access_token: str) -> dict:
    """Aggregate account metrics (latest day)."""
    import time
    from datetime import datetime, timedelta
    end = datetime.utcnow()
    start = end - timedelta(days=1)
    since_ts = int(start.timestamp())
    until_ts = int(end.timestamp())
    out = {}
    for metric in ["reach", "accounts_engaged", "follower_count"]:
        try:
            data = get_user_insights(access_token, metric, period="day", since=str(since_ts), until=str(until_ts))
            for item in data.get("data") or []:
                values = item.get("values") or []
                if values and "value" in values[0]:
                    out[metric] = values[0]["value"]
                    break
        except Exception:
            pass
    return out


def get_follower_growth(access_token: str, days: int = 30) -> list[dict]:
    """Follower count over time (daily points)."""
    from datetime import datetime, timedelta
    end = datetime.utcnow()
    start = end - timedelta(days=days)
    since_ts = int(start.timestamp())
    until_ts = int(end.timestamp())
    data = get_user_insights(access_token, "follower_count", period="day", since=str(since_ts), until=str(until_ts))
    points = []
    for item in data.get("data") or []:
        for v in item.get("values") or []:
            if "end_time" in v and "value" in v:
                # end_time is ISO like 2025-02-28T00:00:00+0000
                end_time = v["end_time"][:10]
                points.append({"date": end_time, "value": v["value"]})
    points.sort(key=lambda x: x["date"])
    return points
