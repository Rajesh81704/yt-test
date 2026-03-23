from celery import Celery
from celery.utils.log import get_task_logger
from pathlib import Path
from dotenv import load_dotenv
import logging
import os
import yt_dlp

load_dotenv()

logging.basicConfig(
    level=logging.DEBUG,
    format="%(asctime)s [%(levelname)s] %(name)s — %(message)s",
    datefmt="%H:%M:%S",
    force=True,
)
log = get_task_logger(__name__)

from urllib.parse import quote
_host = os.getenv("REDIS_HOST", "localhost")
_port = os.getenv("REDIS_PORT", "6379")
_user = quote(os.getenv("REDIS_USERNAME", ""), safe="")
_pass = quote(os.getenv("REDIS_PASSWORD", ""), safe="")
_auth = f"{_user}:{_pass}@" if _pass else ""
REDIS_URL = f"redis://{_auth}{_host}:{_port}/0"

log.info(f"Redis: {_host}:{_port}")

celery = Celery("ytdl", broker=REDIS_URL, backend=REDIS_URL)
celery.conf.update(
    task_track_started=True,
    broker_transport_options={"visibility_timeout": 3600},
    result_expires=3600,
)

COOKIES_PATH = Path(__file__).parent / "cookies.txt"


def find_cookies() -> str | None:
    for p in (COOKIES_PATH, Path.home() / "cookies.txt"):
        if p.exists() and p.stat().st_size > 100:
            log.info(f"Using cookies: {p}")
            return str(p)
    log.warning("No cookies.txt found")
    return None


@celery.task(bind=True)
def extract_formats(self, url: str) -> dict:
    log.info(f"[{self.request.id[:8]}] Task started — {url}")
    self.update_state(state="PROGRESS", meta={"message": "Extracting formats..."})

    ydl_opts = {"quiet": False, "skip_download": True, "verbose": False}
    cookies = find_cookies()
    if cookies:
        ydl_opts["cookiefile"] = cookies

    try:
        log.debug(f"[{self.request.id[:8]}] Calling yt_dlp.extract_info...")
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
        log.info(f"[{self.request.id[:8]}] Extracted: {info.get('title')}")
    except Exception as e:
        log.error(f"[{self.request.id[:8]}] yt_dlp error: {e}")
        raise

    formats = sorted(
        info.get("formats", []),
        key=lambda f: (f.get("height") or 0, f.get("abr") or 0),
        reverse=True,
    )
    log.info(f"[{self.request.id[:8]}] Found {len(formats)} formats")

    return {
        "title":      info.get("title"),
        "duration":   info.get("duration"),
        "thumbnail":  info.get("thumbnail"),
        "uploader":   info.get("uploader"),
        "view_count": info.get("view_count"),
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
                "abr":             f.get("abr"),
                "vbr":             f.get("vbr"),
                "filesize":        f.get("filesize"),
                "filesize_approx": f.get("filesize_approx"),
                "protocol":        f.get("protocol"),
                "download_url":    f.get("url"),
            }
            for f in formats
        ],
    }
