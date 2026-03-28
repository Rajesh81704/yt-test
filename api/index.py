from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pathlib import Path
import yt_dlp
import random
import asyncio
import os
from concurrent.futures import ThreadPoolExecutor

app = FastAPI(title="Video Format Extractor", version="1.0.0")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

_executor = ThreadPoolExecutor(max_workers=8)


# ── Proxy config ──────────────────────────────────────────────────────────────
def _load_proxies() -> list[str]:
    # On Vercel: set PROXIES env var as comma-separated proxy URLs
    env_proxies = os.environ.get("PROXIES", "")
    if env_proxies:
        return [p.strip() for p in env_proxies.split(",") if p.strip()]
    p = Path(__file__).parent.parent / "proxies.properties"
    if not p.exists():
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

def get_proxy() -> str | None:
    return random.choice(PROXIES) if PROXIES else None


def _get_note(url: str) -> str:
    if "youtube.com" in url or "youtu.be" in url:
        return "High-res formats (720p+) are video-only. Pair with an audio-only format and merge on the client."
    return "Some formats may be video-only or audio-only. Merge on the client if needed."


# ── Models ────────────────────────────────────────────────────────────────────
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


class VideoResponse(BaseModel):
    title: str | None
    note: str
    extractor: str
    formats: list[FormatInfo]


# ── yt-dlp extractor ──────────────────────────────────────────────────────────
def _extract(url: str, proxy: str | None) -> dict:
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "format": "bestvideo*+bestaudio*/best",
        "extractor_args": {
            "youtube": {
                "player_client": ["android_vr", "web_safari"],
            }
        },
        "socket_timeout": 15,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Linux; Android 12; Pixel 6) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0.0.0 Mobile Safari/537.36"
        },
    }

    if proxy:
        ydl_opts["proxy"] = proxy

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    formats = sorted(
        [f for f in info.get("formats", []) if f.get("url")],
        key=lambda x: (x.get("height") or 0, x.get("abr") or 0),
        reverse=True,
    )

    return {
        "title": info.get("title"),
        "note": _get_note(url),
        "extractor": "yt-dlp",
        "formats": [
            {
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
                "has_video":       f.get("vcodec") not in (None, "none"),
                "has_audio":       f.get("acodec") not in (None, "none"),
                "download_url":    f.get("url"),
            }
            for f in formats
        ],
    }


def get_formats_ytdlp(url: str, max_retries: int = 3) -> dict:
    last_err = None
    tried: set = set()
    for _ in range(max_retries):
        proxy = get_proxy()
        while proxy in tried and len(tried) < len(PROXIES):
            proxy = get_proxy()
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
@app.post("/formats", response_model=VideoResponse)
async def formats(body: VideoRequest):
    url = body.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="Missing 'url'")
    try:
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(_executor, get_formats_ytdlp, url)
    except yt_dlp.utils.DownloadError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
