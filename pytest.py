import yt_dlp

def get_formats(url):
    ydl_opts = {
        "quiet": True,
        "skip_download": True
    }

    with yt_dlp.YoutubeDL(ydl_opts) as ydl:
        info = ydl.extract_info(url, download=False)

    # Filter only MP4 formats WITH audio
    formats = [
        f for f in info["formats"]
        if (
            f.get("url") and
            f.get("ext") == "mp4" and
            f.get("acodec") != "none"
        )
    ]

    # Sort by resolution (best first)
    formats = sorted(
        formats,
        key=lambda x: x.get("height") or 0,
        reverse=True
    )

    return formats

def print_formats(formats):
    print("\n🎬 Available Formats (MP4 with Audio):\n")

    for i, f in enumerate(formats):
        print(f"Option {i+1}")
        print("-----------------------------------")
        print("Quality:", f.get("format_note"))
        print("Resolution:", f.get("resolution"))
        print("File Size:", f.get("filesize"))
        print("Audio Codec:", f.get("acodec"))
        print("URL:", f.get("url"))
        print()


if __name__ == "__main__":
    url = input("Enter YouTube URL: ")
    formats = get_formats(url)
    if not formats:
        print("❌ No MP4 formats with audio found.")
    else:
        print_formats(formats)