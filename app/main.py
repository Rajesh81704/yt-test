from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI(title="Video Formats API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

@app.api_route("/{path:path}", methods=["GET", "POST"])
async def debug_catch_all(request: Request, path: str):
    return {
        "status": "ok",
        "captured_path": path,
        "scope_path": request.scope.get("path"),
        "headers": dict(request.headers)
    }




@app.get("/health")
async def health():
    return {"status": "ok"}


@app.post("/formats")
async def unified_formats(body: FormatRequest):
    url = body.url.strip()
    if not url:
        raise HTTPException(status_code=400, detail="Missing 'url'")

    loop = asyncio.get_event_loop()

    try:
        if "instagram.com" in url:
            return await loop.run_in_executor(_executor, get_insta_formats, url)
        elif any(domain in url for domain in FB_DOMAINS):
            return await loop.run_in_executor(_executor, get_fb_formats, url)
        else:
            return await loop.run_in_executor(_executor, get_yt_formats, url)
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))



