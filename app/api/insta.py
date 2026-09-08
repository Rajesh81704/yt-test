from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import yt_dlp
import asyncio
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from app.api.utils import extract_with_retry, build_formats
import re

router = APIRouter(prefix="/social/insta", tags=["Instagram"])
_executor = ThreadPoolExecutor(max_workers=8)

COOKIES_PATH = Path(__file__).parent / "cookies.txt"


def find_cookies() -> str | None:
    """Find cookies.txt in app/api/ or home directory."""
    for p in (COOKIES_PATH, Path.home() / "cookies.txt"):
        if p.exists() and p.stat().st_size > 100:
            return str(p)
    return None


def normalize_instagram_url(url: str) -> str:
    """Convert Instagram URL to embed URL which is sometimes more accessible."""
    # Extract post ID from URL
    match = re.search(r'/(?:p|reel)/([A-Za-z0-9_-]+)', url)
    if match:
        post_id = match.group(1)
        # Return both original and embed URLs to try
        return url, f"https://www.instagram.com/p/{post_id}/embed/"
    return url, None


def get_ydl_opts(use_embed: bool = False) -> dict:
    """Build yt-dlp options with cookie support and iPhone emulation for Instagram."""
    opts = {
        "quiet": False,  # Enable verbose logging to debug
        "skip_download": True,
        "socket_timeout": 30,
        "format": "best",
        # Instagram-specific extractor arguments - try different API endpoints
        "extractor_args": {
            "instagram": {
                "api": ["graphql", "mobile", "web"],  # Try GraphQL first, then mobile, then web
            }
        },
        # Emulate iPhone Safari - Instagram is less aggressive with mobile
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_5_1 like Mac OS X) "
                          "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.5 Mobile/15E148 Safari/604.1",
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Accept-Encoding": "gzip, deflate, br",
            "DNT": "1",
            "Connection": "keep-alive",
            "Upgrade-Insecure-Requests": "1",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "none",
        },
    }
    
    # Try using cookies from browser directly first
    try:
        opts["cookiesfrombrowser"] = ("firefox",)
        print("[instagram] Using cookies from Firefox with iPhone Safari emulation", flush=True)
    except Exception as e:
        print(f"[instagram] Could not access Firefox cookies: {e}", flush=True)
        # Fallback to cookies file if available
        cookies = find_cookies()
        if cookies:
            opts["cookiefile"] = cookies
            print(f"[instagram] Using cookies from file: {cookies}", flush=True)
        else:
            print("[instagram] WARNING: No cookies available - download will likely fail", flush=True)
    
    return opts


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


def _get_formats(url: str) -> dict:
    """Extract Instagram video formats with retry logic."""
    ydl_opts = get_ydl_opts()
    
    # Try original URL first
    try:
        print(f"[instagram] Attempting to extract from: {url}", flush=True)
        info = extract_with_retry(url, ydl_opts)
        raw = [f for f in info.get("formats", []) if f.get("url")]
        if raw:  # Success!
            print(f"[instagram] Successfully extracted {len(raw)} formats", flush=True)
            return {
                "title": info.get("title"), 
                "platform": "instagram", 
                "extractor": "yt-dlp", 
                "formats": build_formats(raw)
            }
    except Exception as e:
        print(f"[instagram] First attempt failed: {e}", flush=True)
    
    # If that fails, try with embed URL
    original_url, embed_url = normalize_instagram_url(url)
    if embed_url and embed_url != url:
        try:
            print(f"[instagram] Retrying with embed URL: {embed_url}", flush=True)
            info = extract_with_retry(embed_url, ydl_opts)
            raw = [f for f in info.get("formats", []) if f.get("url")]
            if raw:
                print(f"[instagram] Embed URL succeeded with {len(raw)} formats", flush=True)
                return {
                    "title": info.get("title"), 
                    "platform": "instagram", 
                    "extractor": "yt-dlp", 
                    "formats": build_formats(raw)
                }
        except Exception as e:
            print(f"[instagram] Embed attempt also failed: {e}", flush=True)
    
    # If everything fails, raise the original error
    raise Exception("Unable to extract Instagram video. The post may be private, deleted, or Instagram is blocking access.")


@router.post("/formats", response_model=VideoResponse, summary="Get Instagram video formats")
async def insta_formats(body: VideoRequest):
    url = body.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="Missing 'url'")
    if "instagram.com" not in url:
        raise HTTPException(status_code=400, detail="URL must be an Instagram link")
    try:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, _get_formats, url)
    except yt_dlp.utils.DownloadError as e:
        error_msg = str(e)
        
        # Provide helpful error messages
        if "empty media response" in error_msg.lower():
            raise HTTPException(
                status_code=403, 
                detail="Instagram blocked access to this post. Possible reasons:\n"
                       "1. The post is from a private account you don't follow\n"
                       "2. The post has been deleted\n"
                       "3. Instagram is blocking automated access (try again later)\n"
                       "4. Your cookies are expired - try logging out and back into Instagram in Firefox"
            )
        elif "login" in error_msg.lower() or "cookie" in error_msg.lower():
            raise HTTPException(
                status_code=401,
                detail="Instagram requires authentication. Make sure you're logged into Instagram in Firefox, "
                       "then restart the server."
            )
        else:
            raise HTTPException(status_code=400, detail=error_msg)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
