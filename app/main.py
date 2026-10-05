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
async def fix_path_middleware(request: Request, call_next):
    path = request.scope.get("path", "")
    for prefix in ("/api/index.py", "/api/index", "/api"):
        if path.startswith(prefix) and len(path) > len(prefix) and path[len(prefix)] == "/":
            request.scope["path"] = path[len(prefix):]
            break
        elif path == prefix:
            request.scope["path"] = "/"
            break
    return await call_next(request)


app.include_router(yt_router)
app.include_router(insta_router)
app.include_router(fb_router)


class FormatRequest(BaseModel):
    url: str


@app.get("/")
async def root(request: Request):
    return {
        "status": "ok",
        "scope_path": request.scope.get("path"),
        "raw_path": request.scope.get("raw_path", b"").decode("utf-8", errors="ignore"),
        "headers": dict(request.headers),
        "query_string": request.scope.get("query_string", b"").decode("utf-8", errors="ignore"),
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



