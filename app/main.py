from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
import asyncio
from concurrent.futures import ThreadPoolExecutor

from app.api.yt import router as yt_router, _get_formats as get_yt_formats
from app.api.insta import router as insta_router, _get_formats as get_insta_formats
from app.api.fb import router as fb_router, _get_formats as get_fb_formats, FB_DOMAINS

_executor = ThreadPoolExecutor(max_workers=8)

app = FastAPI(
    title="Video Formats API",
    description="API to extract video formats for YouTube, Instagram, and Facebook",
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json",
)

app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


@app.middleware("http")
async def vercel_path_fix(request: Request, call_next):
    scope_path = request.scope.get("path", "")
    for prefix in ("/api/index.py", "/api/index", "/api"):
        if scope_path.startswith(prefix):
            remainder = scope_path[len(prefix):]
            request.scope["path"] = remainder if remainder else "/"
            break
    return await call_next(request)






app.include_router(yt_router)
app.include_router(insta_router)
app.include_router(fb_router)



class FormatRequest(BaseModel):
    url: str


@app.get("/")
async def root():
    return {
        "status": "ok",
        "message": "Video Formats API is running",
        "endpoints": {
            "docs": "/docs",
            "health": "/health",
            "unified_formats": "POST /formats",
            "youtube_formats": "POST /social/yt/formats",
            "instagram_formats": "POST /social/insta/formats",
            "facebook_formats": "POST /social/fb/formats",
        },
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




