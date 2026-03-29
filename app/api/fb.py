from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import yt_dlp
import asyncio
from concurrent.futures import ThreadPoolExecutor
from app.api.utils import extract_with_retry, build_formats

router = APIRouter(prefix="/social/fb", tags=["Facebook"])
_executor = ThreadPoolExecutor(max_workers=8)

YDL_OPTS = {
    "quiet": True,
    "skip_download": True,
    "socket_timeout": 15,
    "http_headers": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36",
        "Accept-Language": "en-US,en;q=0.9",
    },
}

FB_DOMAINS = ("facebook.com", "fb.watch", "fb.com")


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
    platform: str = "facebook"
    extractor: str
    formats: list[FormatInfo]


def _get_formats(url: str) -> dict:
    info = extract_with_retry(url, YDL_OPTS)
    raw = [f for f in info.get("formats", []) if f.get("url")]
    return {"title": info.get("title"), "platform": "facebook", "extractor": "yt-dlp", "formats": build_formats(raw)}


@router.post("/formats", response_model=VideoResponse, summary="Get Facebook video formats")
async def fb_formats(body: VideoRequest):
    url = body.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="Missing 'url'")
    if not url.startswith("https://") and not url.startswith("http://"):
        raise HTTPException(status_code=400, detail="URL must start with http:// or https://")
    if not any(d in url for d in FB_DOMAINS):
        raise HTTPException(status_code=400, detail="URL must be a Facebook link")
    try:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, _get_formats, url)
    except yt_dlp.utils.DownloadError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
