"""
Extract YouTube format URLs using a headless Playwright browser.
Intercepts the actual network requests YouTube makes to get stream URLs.
"""
import asyncio
import json
import re
from playwright.async_api import async_playwright


async def extract_formats_browser(url: str) -> dict:
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                       "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            viewport={"width": 1280, "height": 720},
        )

        # Load cookies if available
        from pathlib import Path
        cookies_path = Path(__file__).parent / "cookies.txt"
        if cookies_path.exists():
            cookies = _parse_netscape_cookies(cookies_path.read_text())
            if cookies:
                await context.add_cookies(cookies)

        page = await context.new_page()

        # Intercept YouTube's player API response
        player_data = {}

        async def handle_response(response):
            if "youtubei/v1/player" in response.url:
                try:
                    body = await response.json()
                    if "streamingData" in body:
                        player_data["data"] = body
                except Exception:
                    pass

        page.on("response", handle_response)

        await page.goto(url, wait_until="domcontentloaded", timeout=30000)
        # Wait up to 10s for the player API response to be intercepted
        for _ in range(20):
            if player_data:
                break
            await page.wait_for_timeout(500)

        # Fallback: extract ytInitialPlayerResponse from page JS if interception missed it
        if not player_data:
            try:
                embedded = await page.evaluate("() => window.ytInitialPlayerResponse || null")
                if embedded and "streamingData" in embedded:
                    player_data["data"] = embedded
                    print("[browser] Got player data from ytInitialPlayerResponse", flush=True)
            except Exception as js_err:
                print(f"[browser] JS fallback failed: {js_err}", flush=True)

        title = await page.title()
        title = title.replace(" - YouTube", "").strip()

        # Capture cookies for client-side download auth
        raw_cookies = await context.cookies()
        cookie_header = "; ".join(f"{c['name']}={c['value']}" for c in raw_cookies if "youtube" in c.get("domain","") or "google" in c.get("domain",""))

        await browser.close()

    if not player_data:
        raise Exception(
            "Could not intercept YouTube player API response. "
            "The page may have loaded without triggering /youtubei/v1/player. "
            "Check if Playwright chromium is installed: `playwright install chromium`"
        )

    data = player_data["data"]
    streaming = data.get("streamingData", {})
    video_details = data.get("videoDetails", {})

    formats = []

    for f in streaming.get("formats", []):
        formats.append(_parse_format(f, has_video=True, has_audio=True))

    for f in streaming.get("adaptiveFormats", []):
        mime = f.get("mimeType", "")
        if not mime.startswith("video/") and not mime.startswith("audio/"):
            continue  # skip storyboards, images, etc.
        has_video = mime.startswith("video/")
        has_audio = mime.startswith("audio/")
        formats.append(_parse_format(f, has_video=has_video, has_audio=has_audio))

    formats = sorted(
        [f for f in formats if f.get("download_url")],
        key=lambda x: x.get("height") or 0,
        reverse=True,
    )

    return {
        "title": video_details.get("title") or title,
        "duration": int(video_details.get("lengthSeconds", 0)),
        "thumbnail": video_details.get("thumbnail", {}).get("thumbnails", [{}])[-1].get("url"),
        "uploader": video_details.get("author"),
        "view_count": int(video_details.get("viewCount", 0)),
        "note": "High-res formats (720p+) are video-only. Pair with audio-only and merge on client.",
        "download_headers": {
            "Cookie": cookie_header,
            "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
            "Referer": "https://www.youtube.com/",
            "Origin": "https://www.youtube.com",
        },
        "formats": formats,
    }


def _parse_format(f: dict, has_video: bool, has_audio: bool) -> dict:
    mime = f.get("mimeType", "")
    ext = mime.split(";")[0].split("/")[-1] if mime else None
    width = f.get("width")
    height = f.get("height")
    return {
        "format_id":       str(f.get("itag", "")),
        "ext":             ext,
        "quality":         f.get("qualityLabel") or f.get("quality"),
        "resolution":      f"{width}x{height}" if width and height else None,
        "width":           width,
        "height":          height,
        "fps":             f.get("fps"),
        "vcodec":          _codec(mime, "video"),
        "acodec":          _codec(mime, "audio"),
        "filesize":        f.get("contentLength"),
        "filesize_approx": None,
        "has_video":       has_video,
        "has_audio":       has_audio,
        "download_url":    f.get("url"),
    }


def _codec(mime: str, kind: str) -> str | None:
    if not mime.startswith(kind):
        return "none"
    m = re.search(r'codecs="([^"]+)"', mime)
    return m.group(1) if m else None


def _parse_netscape_cookies(text: str) -> list[dict]:
    cookies = []
    for line in text.splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        domain, _, path, secure, expires, name, value = parts[:7]
        cookies.append({
            "name":    name,
            "value":   value,
            "domain":  domain,
            "path":    path,
            "secure":  secure == "TRUE",
            "expires": int(expires) if expires.isdigit() else -1,
        })
    return cookies


# ── Standalone test ───────────────────────────────────────────────────────────
if __name__ == "__main__":
    import sys
    url = sys.argv[1] if len(sys.argv) > 1 else "https://www.youtube.com/watch?v=dQw4w9WgXcQ"
    result = asyncio.run(extract_formats_browser(url))
    print(f"Title: {result['title']}")
    print(f"Formats: {len(result['formats'])}")
    for f in result["formats"][:5]:
        print(f"  {f['quality']} {f['resolution']} video={f['has_video']} audio={f['has_audio']}")
