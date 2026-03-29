from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from pathlib import Path
import yt_dlp
import random
import asyncio
from concurrent.futures import ThreadPoolExecutor

_executor = ThreadPoolExecutor(max_workers=8)

SUPPORTED = ("instagram.com", "facebook.com", "fb.watch", "fb.com")


# ── Proxy config (same root-walk logic) ───────────────────────────────────────
def _load_proxies() -> list[str]:
    p = Path(__file__).parent
    for _ in range(3):
        candidate = p / "proxies.properties"
        if candidate.exists():
            p = candidate
            break
        p = p.parent
    else:
        return []
    urls = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("proxy="):
            urls.append(line.split("=", 1)[1])
            continue
        parts = line.split(":")
        if len(parts) == 4:
            ip, port, user, pwd = parts
            urls.append(f"http://{user}:{pwd}@{ip}:{port}")
        elif len(parts) == 2:
            urls.append(f"http://{line}")
    return urls

PROXIES = _load_proxies()


def _get_proxy() -> str | None:
    return random.choice(PROXIES) if PROXIES else None


def _find_cookies() -> str | None:
    for p in (Path(__file__).parent / "cookies.txt", Path.home() / "cookies.txt"):
        if p.exists() and p.stat().st_size > 100:
            return str(p)
    return None


# ── Router ────────────────────────────────────────────────────────────────────
router = APIRouter(prefix="/social", tags=["Social"])


# ── Models ────────────────────────────────────────────────────────────────────
class SocialRequest(BaseModel):
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


class SocialResponse(BaseModel):
    title: str | None
    platform: str
    extractor: str
    formats: list[FormatInfo]


# ── Extractor ─────────────────────────────────────────────────────────────────
def _extract(url: str, proxy: str | None) -> dict:
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "socket_timeout": 15,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (iPhone; CPU iPhone OS 17_0 like Mac OS X) "
                          "AppleWebKit/605.1.15 (KHTML, like Gecko) Version/17.0 Mobile/15E148 Safari/604.1"
        },
    }
    cookies = _find_cookies()
    if cookies:
        ydl_opts["cookiefile"] = cookies
    if proxy:
        ydl_opts["proxy"] = proxy

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    platform = "instagram" if "instagram" in url else "facebook"

    raw = [f for f in info.get("formats", []) if f.get("url")]

    formats = sorted(
        raw,
        key=lambda x: (x.get("height") or 0, x.get("abr") or 0),
        reverse=True,
    )

    def _fmt(f: dict) -> dict:
        has_v = bool(f.get("vcodec") and f.get("vcodec") != "none") or f.get("width") is not None
        has_a = bool(f.get("acodec") and f.get("acodec") != "none") or f.get("abr") is not None
        return {
            "format_id":       f.get("format_id"),
            "ext":             f.get("ext"),
            "quality":         f.get("format_note"),
            "resolution":      f.get("resolution"),
            "width":           f.get("width"),
            "height":          f.get("height"),
            "fps":             f.get("fps"),
            "vcodec":          f.get("vcodec"),
            "acodec":          f.get("acodec"),
            "filesize":        f.get("filesize"),
            "filesize_approx": f.get("filesize_approx"),
            "has_video":       has_v,
            "has_audio":       has_a,
            "download_url":    f.get("url"),
        }

    result = [_fmt(f) for f in formats]

    # If no format has both video+audio, inject a best_video + best_audio pair note
    has_muxed = any(
        (bool(f.get("vcodec") and f.get("vcodec") != "none") or f.get("width") is not None) and
        (bool(f.get("acodec") and f.get("acodec") != "none") or f.get("abr") is not None)
        for f in raw
    )

    if not has_muxed:
        best_video = next((f for f in raw if (f.get("vcodec") and f.get("vcodec") != "none") or f.get("width")), None)
        best_audio = next((f for f in sorted(raw, key=lambda x: x.get("abr") or 0, reverse=True)
                           if (f.get("acodec") and f.get("acodec") != "none") or f.get("abr")), None)
        if best_video and best_audio:
            result.insert(0, {
                "format_id":       f"{best_video.get('format_id')}+{best_audio.get('format_id')}",
                "ext":             best_video.get("ext"),
                "quality":         "best (video+audio)",
                "resolution":      best_video.get("resolution"),
                "width":           best_video.get("width"),
                "height":          best_video.get("height"),
                "fps":             best_video.get("fps"),
                "vcodec":          best_video.get("vcodec"),
                "acodec":          best_audio.get("acodec"),
                "filesize":        None,
                "filesize_approx": None,
                "has_video":       True,
                "has_audio":       True,
                "download_url":    best_video.get("url"),
                "audio_url":       best_audio.get("url"),
            })

    return {
        "title": info.get("title"),
        "platform": platform,
        "extractor": "yt-dlp",
        "formats": result,
    }


def _get_formats(url: str, max_retries: int = 3) -> dict:
    last_err = None
    tried: set = set()
    for _ in range(max_retries):
        proxy = _get_proxy()
        while proxy in tried and len(tried) < len(PROXIES):
            proxy = _get_proxy()
        tried.add(proxy)
        try:
            return _extract(url, proxy)
        except Exception as e:
            msg = str(e).lower()
            if any(k in msg for k in ("remotedisconnected", "connection", "proxy", "timeout", "ssl")):
                last_err = e
                continue
            raise
    raise last_err


# ── Endpoint ──────────────────────────────────────────────────────────────────
@router.post("/formats", response_model=SocialResponse, summary="Get Instagram/Facebook video formats")
async def social_formats(body: SocialRequest):
    url = body.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="Missing 'url'")
    if not any(s in url for s in SUPPORTED):
        raise HTTPException(status_code=400, detail=f"Only supported: {', '.join(SUPPORTED)}")
    try:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, _get_formats, url)
    except yt_dlp.utils.DownloadError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
