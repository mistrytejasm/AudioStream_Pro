import logging
import asyncio
from pathlib import Path
from typing import Optional
from fastapi import APIRouter, HTTPException, BackgroundTasks, Request
from fastapi.responses import StreamingResponse, FileResponse
from pydantic import BaseModel
from app.models.job import AnalyzeRequest, CreateJobRequest, JobState, MediaAnalysisResult
from app.services.playlist import media_analyzer
from app.services.job_manager import job_manager
from app.config import settings

logger = logging.getLogger(__name__)
router = APIRouter()

class SubstituteUrlRequest(BaseModel):
    url: str

@router.post("/playlists/analyze", response_model=MediaAnalysisResult)
async def analyze_media_url(req: AnalyzeRequest):
    try:
        data = await media_analyzer.analyze_media(req.url)
        return data
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        logger.error(f"Error analyzing URL: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=f"Failed to analyze URL: {str(e)}")

@router.post("/jobs", response_model=JobState)
async def create_job(req: CreateJobRequest):
    if not req.tracks:
        raise HTTPException(status_code=400, detail="No tracks selected for processing")
    job = job_manager.create_job(req)
    return job

@router.get("/jobs/{job_id}", response_model=JobState)
async def get_job_status(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    return job

@router.post("/jobs/{job_id}/tracks/{track_id}/retry")
async def retry_track(job_id: str, track_id: str, background_tasks: BackgroundTasks):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if track_id not in job.tracks:
        raise HTTPException(status_code=404, detail="Track not found")
        
    background_tasks.add_task(job_manager.retry_track, job_id, track_id)
    return {"status": "retry_scheduled", "track_id": track_id}

@router.post("/jobs/{job_id}/tracks/{track_id}/auto-resolve")
async def auto_resolve_track(job_id: str, track_id: str, background_tasks: BackgroundTasks):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if track_id not in job.tracks:
        raise HTTPException(status_code=404, detail="Track not found")

    background_tasks.add_task(job_manager.auto_resolve_track, job_id, track_id)
    return {"status": "auto_resolve_scheduled", "track_id": track_id}

@router.post("/jobs/{job_id}/tracks/{track_id}/substitute")
async def substitute_track_url(job_id: str, track_id: str, req: SubstituteUrlRequest, background_tasks: BackgroundTasks):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")
    if track_id not in job.tracks:
        raise HTTPException(status_code=404, detail="Track not found")
    if not req.url:
        raise HTTPException(status_code=400, detail="Invalid URL")

    background_tasks.add_task(job_manager.retry_track, job_id, track_id, custom_url=req.url)
    return {"status": "substitute_scheduled", "track_id": track_id, "url": req.url}

@router.get("/jobs/{job_id}/stream")
async def stream_job_progress(job_id: str, request: Request):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    q = await job_manager.subscribe(job_id)

    async def event_generator():
        try:
            while True:
                if await request.is_disconnected():
                    break
                try:
                    data = await asyncio.wait_for(q.get(), timeout=15.0)
                    yield f"data: {data}\n\n"
                except asyncio.TimeoutError:
                    yield ": ping\n\n"
        finally:
            job_manager.unsubscribe(job_id, q)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        }
    )

@router.get("/jobs/{job_id}/download")
async def download_job_zip(job_id: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    job_output_dir = settings.OUTPUT_DIR / job_id
    zip_files = list(job_output_dir.glob("*.zip"))
    if not zip_files or not zip_files[0].exists():
        raise HTTPException(status_code=404, detail="ZIP package not found")

    zip_path = zip_files[0]
    return FileResponse(
        path=zip_path,
        media_type="application/zip",
        filename=zip_path.name
    )

@router.get("/jobs/{job_id}/files/{filename}")
async def download_single_file(job_id: str, filename: str):
    job = job_manager.get_job(job_id)
    if not job:
        raise HTTPException(status_code=404, detail="Job not found")

    file_path = (settings.OUTPUT_DIR / job_id / filename).resolve()
    if not str(file_path).startswith(str(settings.OUTPUT_DIR.resolve())):
        raise HTTPException(status_code=403, detail="Forbidden")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="File not found")

    ext = file_path.suffix.lower()
    if ext == ".mp4":
        media_type = "video/mp4"
    elif ext == ".m4a":
        media_type = "audio/mp4"
    else:
        media_type = "audio/mpeg"

    return FileResponse(
        path=file_path,
        media_type=media_type,
        filename=file_path.name
    )
