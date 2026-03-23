from fastapi import FastAPI, HTTPException
from pydantic import BaseModel
from pathlib import Path
import yt_dlp

app = FastAPI(title="YT Format Extractor", version="1.0.0")

COOKIES_PATH = Path(__file__).parent / "cookies.txt"


def find_cookies() -> str | None:
    for p in (COOKIES_PATH, Path.home() / "cookies.txt"):
        if p.exists() and p.stat().st_size > 100:
            return str(p)
    return None


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
    formats: list[FormatInfo]


# Exact same ydl_opts as pytest.py
def get_formats(url: str) -> dict:
    ydl_opts = {
        "quiet": True,
        "skip_download": True,
        "extractor_args": {"youtube": {"player_client": ["ios", "android", "web"]}},
    }
    cookies = find_cookies()
    if cookies:
        ydl_opts["cookiefile"] = cookies

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    formats = [
        f for f in info["formats"]
        if f.get("url")
    ]

    formats = sorted(formats, key=lambda x: x.get("height") or 0, reverse=True)

    return {
        "title": info.get("title"),
        "note": "High-res formats (720p+) are video-only. Pair with an audio-only format and merge on the client.",
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


@app.post("/formats", response_model=VideoResponse, summary="Get MP4 formats with audio")
def formats(body: VideoRequest):
    url = body.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="Missing 'url'")
    try:
        return get_formats(url)
    except yt_dlp.utils.DownloadError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        import traceback
        traceback.print_exc()
        raise HTTPException(status_code=500, detail=str(e))
