from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.api.yt import router as yt_router
from app.api.insta import router as insta_router
from app.api.fb import router as fb_router

app = FastAPI(title="Video Formats API")
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])

app.include_router(yt_router)
app.include_router(insta_router)
app.include_router(fb_router)
