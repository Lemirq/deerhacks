"""
Instagram analytics API — self-contained FastAPI router.
Mount in main.py with: app.include_router(instagram_routes.router, prefix="/api/instagram", tags=["instagram"])
"""
from fastapi import APIRouter, Depends
from . import instagram_service
from .instagram_auth import get_current_user_and_ig_token
from .instagram_models import ReelItem, ReelsListResponse

router = APIRouter()


@router.get("/account/overview")
def account_overview(user_and_token=Depends(get_current_user_and_ig_token)):
    _, ig_token = user_and_token
    return instagram_service.get_account_overview(ig_token)


@router.get("/account/follower-growth")
def follower_growth(days: int = 30, user_and_token=Depends(get_current_user_and_ig_token)):
    if days < 1 or days > 365:
        days = 30
    _, ig_token = user_and_token
    return instagram_service.get_follower_growth(ig_token, days=days)


@router.get("/reels")
def reels_list(user_and_token=Depends(get_current_user_and_ig_token)):
    _, ig_token = user_and_token
    data = instagram_service.get_me_media(ig_token)
    items = []
    for node in data.get("data") or []:
        if node.get("media_type") == "REELS":
            items.append(ReelItem(
                id=node["id"],
                caption=node.get("caption"),
                media_url=node.get("media_url"),
                thumbnail_url=node.get("thumbnail_url"),
                timestamp=node.get("timestamp"),
                like_count=node.get("like_count"),
                comments_count=node.get("comments_count"),
                permalink=node.get("permalink"),
            ))
    return ReelsListResponse(data=items)


@router.get("/reels/{media_id}/insights")
def reel_insights(media_id: str, user_and_token=Depends(get_current_user_and_ig_token)):
    _, ig_token = user_and_token
    return instagram_service.get_media_insights(media_id, ig_token)
