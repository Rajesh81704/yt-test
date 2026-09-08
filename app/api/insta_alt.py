"""
Alternative Instagram downloader using instaloader library.
Use this if yt-dlp continues to fail.
"""
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import instaloader
import re
import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

router = APIRouter(prefix="/social/insta-alt", tags=["Instagram-Alternative"])
_executor = ThreadPoolExecutor(max_workers=4)


class VideoRequest(BaseModel):
    url: str


class FormatInfo(BaseModel):
    format_id: str | None
    ext: str | None
    quality: str | None
    resolution: str | None
    width: int | None
    height: int | None
    fps: float | None
    vcodec: str | None
    acodec: str | None
    filesize: int | None
    filesize_approx: int | None
    has_video: bool
    has_audio: bool
    download_url: str | None
    audio_url: str | None = None


class VideoResponse(BaseModel):
    title: str | None
    platform: str = "instagram"
    extractor: str
    formats: list[FormatInfo]


def extract_shortcode(url: str) -> str:
    """Extract Instagram shortcode from URL."""
    match = re.search(r'/(?:p|reel|tv)/([A-Za-z0-9_-]+)', url)
    if match:
        return match.group(1)
    raise ValueError("Invalid Instagram URL format")


def _get_formats_instaloader(url: str) -> dict:
    """Extract Instagram video using instaloader library."""
    try:
        # Initialize instaloader
        L = instaloader.Instaloader(
            download_videos=False,
            download_video_thumbnails=False,
            download_geotags=False,
            download_comments=False,
            save_metadata=False,
            compress_json=False,
        )
        
        # Try to load session from cookies if available
        session_file = Path(__file__).parent / "instagram_session"
        if session_file.exists():
            try:
                L.load_session_from_file("instagram_user", session_file)
                print("[instaloader] Loaded session from file", flush=True)
            except Exception as e:
                print(f"[instaloader] Could not load session: {e}", flush=True)
        
        # Extract shortcode and get post
        shortcode = extract_shortcode(url)
        post = instaloader.Post.from_shortcode(L.context, shortcode)
        
        formats = []
        
        # Handle video posts
        if post.is_video:
            video_url = post.video_url
            formats.append({
                "format_id": "video",
                "ext": "mp4",
                "quality": "best",
                "resolution": f"{post.video_view_count}p" if post.video_view_count else None,
                "width": None,
                "height": None,
                "fps": None,
                "vcodec": "h264",
                "acodec": "aac",
                "filesize": None,
                "filesize_approx": None,
                "has_video": True,
                "has_audio": True,
                "download_url": video_url,
                "audio_url": None,
            })
        
        # Handle image posts (for reels with thumbnails)
        if post.url:
            formats.append({
                "format_id": "thumbnail",
                "ext": "jpg",
                "quality": "best",
                "resolution": None,
                "width": None,
                "height": None,
                "fps": None,
                "vcodec": None,
                "acodec": None,
                "filesize": None,
                "filesize_approx": None,
                "has_video": False,
                "has_audio": False,
                "download_url": post.url,
                "audio_url": None,
            })
        
        if not formats:
            raise Exception("No downloadable content found in this post")
        
        return {
            "title": post.caption[:100] if post.caption else f"Instagram Post {shortcode}",
            "platform": "instagram",
            "extractor": "instaloader",
            "formats": formats,
        }
        
    except instaloader.exceptions.LoginRequiredException:
        raise HTTPException(
            status_code=401,
            detail="This post requires login. Please authenticate instaloader first."
        )
    except instaloader.exceptions.PrivateProfileNotFollowedException:
        raise HTTPException(
            status_code=403,
            detail="This is a private profile that you don't follow."
        )
    except instaloader.exceptions.PostChangedException:
        raise HTTPException(
            status_code=404,
            detail="This post has been deleted or is no longer available."
        )
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to extract Instagram post: {str(e)}")


@router.post("/formats", response_model=VideoResponse, summary="Get Instagram video formats (Alternative)")
async def insta_formats_alt(body: VideoRequest):
    """
    Alternative Instagram endpoint using instaloader library.
    Use this if the main /social/insta endpoint fails.
    """
    url = body.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="Missing 'url'")
    if "instagram.com" not in url:
        raise HTTPException(status_code=400, detail="URL must be an Instagram link")
    
    try:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, _get_formats_instaloader, url)
    except HTTPException:
        raise
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/login", summary="Login to Instagram for instaloader")
async def insta_login(username: str, password: str):
    """
    Authenticate with Instagram to access private content.
    Stores session for future requests.
    """
    try:
        L = instaloader.Instaloader()
        L.login(username, password)
        
        # Save session
        session_file = Path(__file__).parent / "instagram_session"
        L.save_session_to_file(session_file)
        
        return {"status": "success", "message": "Logged in and session saved"}
    except Exception as e:
        raise HTTPException(status_code=401, detail=f"Login failed: {str(e)}")
