from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
import yt_dlp
import asyncio
import shutil
from concurrent.futures import ThreadPoolExecutor
from app.api.utils import extract_with_retry, build_formats

router = APIRouter(prefix="/social/yt", tags=["YouTube"])
_executor = ThreadPoolExecutor(max_workers=8)


def _js_runtimes() -> dict:
    """Return a js_runtimes config if node/deno is available on PATH."""
    for runtime in ("node", "deno"):
        path = shutil.which(runtime)
        if path:
            return {runtime: {"path": path}}
    return {}


YDL_OPTS = {
    "quiet": True,
    "skip_download": True,
    "noplaylist": True,
    # visionos client: returns full HTTPS format list without PO token, works without login
    "extractor_args": {"youtube": {"player_client": ["visionos"]}},
    "js_runtimes": _js_runtimes(),
    "socket_timeout": 10,
    "http_headers": {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                      "AppleWebKit/537.36 (KHTML, like Gecko) "
                      "Chrome/125.0.0.0 Safari/537.36"
    },
}


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
    note: str
    extractor: str
    formats: list[FormatInfo]


def _get_formats(url: str) -> dict:
    info = extract_with_retry(url, YDL_OPTS)
    raw = [f for f in info.get("formats", []) if f.get("url")]
    note = (
        "High-res formats (720p+) are video-only. Pair with an audio-only format and merge on the client."
        if "youtube.com" in url or "youtu.be" in url
        else "Some formats may be video-only or audio-only."
    )
    return {"title": info.get("title"), "note": note, "extractor": "yt-dlp", "formats": build_formats(raw, strict_audio=True)}


@router.post("/formats", response_model=VideoResponse, summary="Get YouTube video formats")
async def yt_formats(body: VideoRequest):
    url = body.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="Missing 'url'")
    try:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, _get_formats, url)
    except yt_dlp.utils.DownloadError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import traceback; traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
