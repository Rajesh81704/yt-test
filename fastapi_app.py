import httpx
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from pathlib import Path
import yt_dlp
import os
import random

app = FastAPI(title="YT Format Extractor", version="1.0.0")

COOKIES_PATH = Path(__file__).parent / "cookies.txt"

# ── Proxy config ─────────────────────────────────────────────────────────────
def _load_proxies() -> list[str]:
    p = Path(__file__).parent / "proxies.properties"
    if not p.exists():
        return []
    urls = []
    for line in p.read_text().splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        # Full URL: proxy=http://...
        if line.startswith("proxy="):
            urls.append(line.split("=", 1)[1])
            continue
        # ip:port:user:pass
        parts = line.split(":")
        if len(parts) == 4:
            ip, port, user, pwd = parts
            urls.append(f"http://{user}:{pwd}@{ip}:{port}")
        # ip:port (no auth)
        elif len(parts) == 2:
            urls.append(f"http://{line}")
    return urls

PROXIES = _load_proxies()

def get_proxy() -> str | None:
    if not PROXIES:
        return None
    return random.choice(PROXIES)


def find_cookies() -> str | None:
    for p in (COOKIES_PATH, Path.home() / "cookies.txt"):
        if p.exists() and p.stat().st_size > 100:
            return str(p)
    return None


# ── Bot-detection error keywords ─────────────────────────────────────────────
_BOT_ERRORS = (
    "sign in to confirm",
    "not a bot",
    "bot detection",
    "cookies",
    "429",
    "too many requests",
)

def _is_bot_error(msg: str) -> bool:
    low = msg.lower()
    return any(k in low for k in _BOT_ERRORS)


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
    extractor: str  # "yt-dlp" or "browser"
    download_headers: dict | None = None
    formats: list[FormatInfo]


# ── yt-dlp extractor ──────────────────────────────────────────────────────────
def get_formats_ytdlp(url: str) -> dict:
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "extractor_args": {"youtube": {"player_client": ["mweb", "ios", "android", "web"]}},
        "compat_opts": set(),
        "socket_timeout": 10,
        "http_headers": {
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                          "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        },
    }
    cookies = find_cookies()
    if cookies:
        ydl_opts["cookiefile"] = cookies

    proxy = get_proxy()
    if proxy:
        safe = proxy.split("@")[-1]
        print(f"[proxy] Using: {safe}", flush=True)
        ydl_opts["proxy"] = proxy
    else:
        print("[proxy] No proxy configured", flush=True)

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    formats = sorted(
        [f for f in info["formats"] if f.get("url")],
        key=lambda x: x.get("height") or 0,
        reverse=True,
    )

    return {
        "title": info.get("title"),
        "note": "High-res formats (720p+) are video-only. Pair with an audio-only format and merge on the client.",
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


# ── Browser extractor (fallback) ──────────────────────────────────────────────
async def get_formats_browser(url: str) -> dict:
    import asyncio
    import concurrent.futures
    from browser_extractor import extract_formats_browser
    print("[browser] Falling back to Playwright browser extractor", flush=True)

    def _run():
        import sys
        loop = asyncio.new_event_loop()
        # Playwright requires ProactorEventLoop on Windows for subprocess support
        if sys.platform == "win32":
            loop = asyncio.ProactorEventLoop()
        asyncio.set_event_loop(loop)
        try:
            return loop.run_until_complete(extract_formats_browser(url))
        finally:
            loop.close()

    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as pool:
        result = await asyncio.get_event_loop().run_in_executor(pool, _run)

    result.setdefault("note", "High-res formats (720p+) are video-only. Pair with an audio-only format and merge on the client.")
    result["extractor"] = "browser"
    return result


# ── Unified endpoint ──────────────────────────────────────────────────────────
@app.post("/formats", response_model=VideoResponse, summary="Get video formats")
async def formats(body: VideoRequest):
    url = body.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="Missing 'url'")

    # 1. Try yt-dlp first (fast)
    try:
        return get_formats_ytdlp(url)
    except yt_dlp.utils.DownloadError as e:
        err = str(e)
        if _is_bot_error(err):
            print(f"[yt-dlp] Bot detection hit, switching to browser extractor", flush=True)
        else:
            raise HTTPException(status_code=400, detail=err)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))

    # 2. Fallback: Playwright browser
    try:
        return await get_formats_browser(url)
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=502, detail=f"Both extractors failed. Browser error: {e}")


class ProxyDownloadRequest(BaseModel):
    url: str
    headers: dict | None = None


@app.post("/proxy-download", summary="Proxy a stream URL through the server")
async def proxy_download(body: ProxyDownloadRequest):
    """
    Fetches the video/audio stream server-side and pipes it to the client.
    Use this when the stream URL requires session-bound cookies/headers.
    Pass the `download_headers` from /formats response as `headers`.
    """
    default_headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                      "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        "Referer": "https://www.youtube.com/",
        "Origin": "https://www.youtube.com",
    }
    req_headers = {**default_headers, **(body.headers or {})}

    client = httpx.AsyncClient(follow_redirects=True, timeout=30)
    req = client.build_request("GET", body.url, headers=req_headers)
    response = await client.send(req, stream=True)

    if response.status_code != 200:
        await client.aclose()
        raise HTTPException(status_code=response.status_code, detail="Stream fetch failed")

    content_type = response.headers.get("content-type", "video/mp4")
    content_length = response.headers.get("content-length")

    resp_headers = {"Content-Type": content_type}
    if content_length:
        resp_headers["Content-Length"] = content_length

    async def stream_chunks():
        try:
            async for chunk in response.aiter_bytes(chunk_size=65536):
                yield chunk
        finally:
            await response.aclose()
            await client.aclose()

    return StreamingResponse(stream_chunks(), headers=resp_headers)
