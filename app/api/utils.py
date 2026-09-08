from pathlib import Path
import random


def load_proxies() -> list[str]:
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


PROXIES = load_proxies()


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

    for p in (Path(__file__).parent / "cookies.txt", Path.home() / "cookies.txt"):
        if p.exists() and p.stat().st_size > 100:
            try:
                shutil.copyfile(p, tmp_cookies)
                return str(tmp_cookies)
            except Exception:
                return str(p)
    return None


def has_video(f: dict) -> bool:
    return bool(f.get("vcodec") and f.get("vcodec") != "none") or f.get("width") is not None


def has_audio(f: dict, strict: bool = False) -> bool:
    """strict=True: only trust acodec field (used for YouTube).
    In all cases, explicit acodec='none' means no audio."""
    acodec = f.get("acodec")
    if acodec == "none":
        return False
    if strict:
        return bool(acodec)
    return bool(acodec) or f.get("abr") is not None


def fmt_entry(f: dict, extra: dict = {}, strict_audio: bool = False) -> dict:
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
        "has_video":       has_video(f),
        "has_audio":       has_audio(f, strict=strict_audio),
        "download_url":    f.get("url"),
        "audio_url":       None,
        **extra,
    }


def extract_with_retry(url: str, ydl_opts: dict, max_retries: int = 3) -> dict:
    import yt_dlp

    # Keywords that indicate a retryable network / proxy issue
    _RETRYABLE = (
        "remotedisconnected", "connection", "proxy", "timeout", "ssl",
        "429", "too many requests",            # rate-limited proxy
        "sign in to confirm", "bot",           # proxy IP flagged by YouTube
        "http error 4",                        # generic 4xx from proxy
    )

    cookies = find_cookies()

    # Step 1: Try direct connection (no proxy) first.
    # Direct connection generates signed URLs bound to the caller's server IP
    # rather than a third-party proxy IP (which causes HTTP 403 Forbidden in end-user browsers).
    opts = {**ydl_opts}
    opts.pop("proxy", None)
    if cookies:
        opts["cookiefile"] = cookies
    try:
        print("[proxy] trying direct connection first...", flush=True)
        with yt_dlp.YoutubeDL(opts) as ydl:
            return ydl.extract_info(url, download=False)
    except Exception as e:
        msg = str(e).lower()
        if not any(k in msg for k in _RETRYABLE):
            raise  # Non-retryable error — propagate immediately
        print(f"[proxy] direct connection failed ({e}) — falling back to proxies...", flush=True)

    # Step 2: Fallback to rotating proxies if direct connection was blocked/rate-limited
    last_err = None
    tried: set = set()

    for attempt in range(max_retries):
        proxy = get_proxy()
        while proxy in tried and len(tried) < len(PROXIES):
            proxy = get_proxy()
        tried.add(proxy)

        opts = {**ydl_opts}
        if proxy:
            opts["proxy"] = proxy
            print(f"[proxy] attempt {attempt + 1}: {proxy.split('@')[-1]}", flush=True)
        if cookies:
            opts["cookiefile"] = cookies

        try:
            with yt_dlp.YoutubeDL(opts) as ydl:
                return ydl.extract_info(url, download=False)
        except Exception as e:
            msg = str(e).lower()
            if any(k in msg for k in _RETRYABLE):
                print(f"[proxy] retryable error on proxy attempt {attempt + 1}: {e}", flush=True)
                last_err = e
                continue
            raise

    raise last_err or Exception("All direct and proxy extraction attempts failed")



def build_formats(raw: list[dict], strict_audio: bool = False) -> list[dict]:
    """Sort formats and prepend a best video+audio pair if streams are split."""
    sorted_fmts = sorted(raw, key=lambda x: (x.get("height") or 0, x.get("abr") or 0), reverse=True)
    result = [fmt_entry(f, strict_audio=strict_audio) for f in sorted_fmts]

    has_muxed = any(has_video(f) and has_audio(f, strict=strict_audio) for f in raw)
    if not has_muxed:
        best_v = next((f for f in raw if has_video(f)), None)
        best_a = next((f for f in sorted(raw, key=lambda x: x.get("abr") or 0, reverse=True)
                       if has_audio(f, strict=strict_audio)), None)
        if best_v and best_a:
            result.insert(0, fmt_entry(best_v, {
                "format_id": f"{best_v.get('format_id')}+{best_a.get('format_id')}",
                "quality":   "best (video+audio)",
                "acodec":    best_a.get("acodec"),
                "has_audio": True,
                "audio_url": best_a.get("url"),
            }, strict_audio=strict_audio))
    return result
