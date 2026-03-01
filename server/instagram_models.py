"""Pydantic models for Instagram API responses (analytics scope only)."""

from pydantic import BaseModel
from typing import Optional


class AccountOverviewResponse(BaseModel):
    follower_count: Optional[int] = None
    reach: Optional[int] = None
    accounts_engaged: Optional[int] = None


class FollowerGrowthPoint(BaseModel):
    date: str
    value: int


class ReelItem(BaseModel):
    id: str
    caption: Optional[str] = None
    media_url: Optional[str] = None
    thumbnail_url: Optional[str] = None
    timestamp: Optional[str] = None
    like_count: Optional[int] = None
    comments_count: Optional[int] = None
    permalink: Optional[str] = None


class ReelsListResponse(BaseModel):
    data: list[ReelItem]


class ReelInsightsResponse(BaseModel):
    views: Optional[int] = None
    reach: Optional[int] = None
    saved: Optional[int] = None
    shares: Optional[int] = None
    total_interactions: Optional[int] = None
    ig_reels_avg_watch_time: Optional[int] = None
