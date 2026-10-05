from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from pathlib import Path
import yt_dlp
import random
import asyncio
import shutil
from concurrent.futures import ThreadPoolExecutor


# ── JS runtime helper ─────────────────────────────────────────────────────────
def _js_runtimes() -> dict:
    """Return a js_runtimes config dict if node or deno is available on PATH."""
    for runtime in ("node", "deno"):
        path = shutil.which(runtime)
        if path:
            return {runtime: {"path": path}}
    return {}


COOKIES_PATH = Path(__file__).parent / "cookies.txt"
_executor = ThreadPoolExecutor(max_workers=8)

# Keywords that indicate a retryable proxy / network issue
_RETRYABLE = (
    "remotedisconnected", "connection", "proxy", "timeout", "ssl",
    "429", "too many requests",        # rate-limited proxy
    "sign in to confirm", "bot",       # proxy IP flagged by YouTube
    "http error 4",                    # generic 4xx from proxy
)


# ── Proxy config ──────────────────────────────────────────────────────────────
def _load_proxies() -> list[str]:
    """Walk up from app/api/ to find proxies.properties at the project root."""
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


# ── App ───────────────────────────────────────────────────────────────────────
app = FastAPI(title="Video Formats API")
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


def get_proxy() -> str | None:
    return random.choice(PROXIES) if PROXIES else None


def find_cookies() -> str | None:
    import os, shutil, tempfile
    tmp_cookies = Path(tempfile.gettempdir()) / "cookies.txt"
    env_cookies = os.getenv("YOUTUBE_COOKIES") or os.getenv("COOKIES_TEXT")
    if env_cookies:
        try:
            tmp_cookies.write_text(env_cookies, encoding="utf-8")
            return str(tmp_cookies)
        except Exception:
            pass

    for p in (COOKIES_PATH, Path.home() / "cookies.txt"):
        if p.exists() and p.stat().st_size > 100:
            try:
                shutil.copyfile(p, tmp_cookies)
                return str(tmp_cookies)
            except Exception:
                return str(p)
    return None


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
        "noplaylist": True,
        "format": "bestvideo*+bestaudio*/best",
        "extractor_args": {
            "youtube": {
                "player_client": ["ios", "android", "web", "mweb"],
            }
        },
        "js_runtimes": _js_runtimes(),
        "socket_timeout": 10,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
                          "AppleWebKit/537.36 (KHTML, like Gecko) "
                          "Chrome/125.0.0.0 Safari/537.36"
        },
    }

    cookies = find_cookies()
    if cookies:
        ydl_opts["cookiefile"] = cookies

    if proxy:
        ydl_opts["proxy"] = proxy
        print(f"[proxy] {proxy.split('@')[-1]}", flush=True)
    else:
        print("[proxy] none", flush=True)

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
                "has_video":       bool(f.get("vcodec") and f.get("vcodec") != "none") or f.get("width") is not None,
                "has_audio":       bool(f.get("acodec") and f.get("acodec") != "none") or f.get("abr") is not None,
                "download_url":    f.get("url"),
            }
            for f in formats
        ],
    }


def get_formats_ytdlp(url: str, max_retries: int = 3) -> dict:
    # Step 1: Try direct connection (no proxy) first to prevent proxy-IP binding 403 Forbidden errors
    try:
        print("[proxy] trying direct connection first...", flush=True)
        return _extract(url, None)
    except Exception as e:
        msg = str(e).lower()
        if not any(k in msg for k in _RETRYABLE):
            raise
        print(f"[proxy] direct connection failed ({e}) — falling back to proxies...", flush=True)

    # Step 2: Fallback to rotating proxies if direct connection was blocked
    last_err = None
    tried: set = set()
    for attempt in range(max_retries):
        proxy = get_proxy()
        while proxy in tried and len(tried) < len(PROXIES):
            proxy = get_proxy()
        tried.add(proxy)
        try:
            return _extract(url, proxy)
        except Exception as e:
            msg = str(e).lower()
            if any(k in msg for k in _RETRYABLE):
                print(f"[proxy] retryable error on attempt {attempt + 1}: {e}", flush=True)
                last_err = e
                continue
            raise

    raise last_err or Exception("All direct and proxy extraction attempts failed")


# ── Endpoint ──────────────────────────────────────────────────────────────────
@app.post("/formats", response_model=VideoResponse, summary="Get video formats")
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
