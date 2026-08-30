import logging
from pathlib import Path
from contextlib import asynccontextmanager
from fastapi import FastAPI, Response
from fastapi.responses import HTMLResponse, FileResponse
from fastapi.middleware.cors import CORSMiddleware
from app.config import settings
from app.routes.api import router as api_router
from app.services.ffmpeg_finder import get_ffmpeg_paths

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s"
)
logger = logging.getLogger(__name__)

STATIC_INDEX = Path(__file__).parent / "static" / "index.html"

@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info("Initializing Playlist Audio Converter API...")
    try:
        ffmpeg, ffprobe = get_ffmpeg_paths()
        logger.info(f"FFmpeg ready: {ffmpeg}")
        logger.info(f"FFprobe ready: {ffprobe}")
    except Exception as e:
        logger.error(f"FFmpeg initialization error: {e}")
    yield
    logger.info("Shutting down Playlist Audio Converter API...")

app = FastAPI(
    title=settings.PROJECT_NAME,
    lifespan=lifespan
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(api_router, prefix=settings.API_V1_STR)

@app.get("/", response_class=HTMLResponse)
async def get_index():
    if STATIC_INDEX.exists():
        return HTMLResponse(content=STATIC_INDEX.read_text(encoding="utf-8"), status_code=200)
    return HTMLResponse(content="<h1>Playlist Converter</h1>", status_code=200)

@app.get("/favicon.ico")
async def favicon():
    return Response(status_code=204)

@app.get("/health")
async def health_check():
    return {"status": "ok"}
