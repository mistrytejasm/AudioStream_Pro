import asyncio
import logging
import uuid
from pathlib import Path
from typing import Dict, List, Optional
import yt_dlp

from app.config import settings
from app.models.job import JobState, TrackProgress, ItemStatus, JobStatus, CreateJobRequest, TrackSelection, MediaType, Platform
from app.services.converter import converter
from app.services.tagger import tagger, sanitize_filename
from app.services.packager import packager
from app.services.playlist import get_cookies_filepath

logger = logging.getLogger(__name__)

class JobManager:
    def __init__(self):
        self._jobs: Dict[str, JobState] = {}
        self._job_requests: Dict[str, CreateJobRequest] = {}
        self._subscribers: Dict[str, List[asyncio.Queue]] = {}

    def get_job(self, job_id: str) -> Optional[JobState]:
        return self._jobs.get(job_id)

    async def subscribe(self, job_id: str) -> asyncio.Queue:
        q = asyncio.Queue()
        if job_id not in self._subscribers:
            self._subscribers[job_id] = []
        self._subscribers[job_id].append(q)
        if job_id in self._jobs:
            await q.put(self._jobs[job_id].model_dump_json())
        return q

    def unsubscribe(self, job_id: str, q: asyncio.Queue):
        if job_id in self._subscribers and q in self._subscribers[job_id]:
            self._subscribers[job_id].remove(q)

    async def broadcast(self, job_id: str):
        if job_id not in self._jobs or job_id not in self._subscribers:
            return
        msg = self._jobs[job_id].model_dump_json()
        dead = []
        for q in self._subscribers[job_id]:
            try:
                await q.put(msg)
            except Exception:
                dead.append(q)
        for d in dead:
            self.unsubscribe(job_id, d)

    def create_job(self, req: CreateJobRequest) -> JobState:
        job_id = f"job_{uuid.uuid4().hex[:10]}"
        tracks_dict = {}
        for track in req.tracks:
            tracks_dict[track.id] = TrackProgress(
                id=track.id,
                title=track.title,
                position=track.position,
                status=ItemStatus.PENDING,
                progress=0
            )

        job = JobState(
            job_id=job_id,
            platform=req.platform,
            media_type=req.media_type,
            playlist_title=req.playlist_title,
            format=req.format,
            status=JobStatus.QUEUED,
            total_tracks=len(req.tracks),
            completed_tracks=0,
            failed_tracks=0,
            tracks=tracks_dict
        )
        self._jobs[job_id] = job
        self._job_requests[job_id] = req
        logger.info(f"Created Job [{job_id}] (Platform: {req.platform}, Type: {req.media_type}, Format: {req.format}) for '{req.playlist_title}'")
        
        asyncio.create_task(self._process_job(job_id, req))
        return job

    def repackage_zip(self, job_id: str):
        job = self._jobs.get(job_id)
        if not job or job.media_type == MediaType.SINGLE:
            return
        job_output_dir = settings.OUTPUT_DIR / job_id
        media_files = list(job_output_dir.glob("*.m4a")) + list(job_output_dir.glob("*.mp3")) + list(job_output_dir.glob("*.mp4"))
        if media_files:
            zip_filename = f"{sanitize_filename(job.playlist_title)}_{job.format.upper()}.zip"
            zip_path = job_output_dir / zip_filename
            packager.create_zip(media_files, zip_path)
            job.zip_download_url = f"/api/v1/jobs/{job_id}/download"
            logger.info(f"✓ ZIP package updated with {len(media_files)} files at {zip_path.name}")

    async def _execute_single_track(
        self,
        job_id: str,
        track: TrackSelection,
        format_val: str,
        playlist_title: str,
        total_count: int,
        target_url: Optional[str] = None
    ) -> bool:
        job = self._jobs[job_id]
        track_progress = job.tracks[track.id]
        track_num_str = f"{track.position:02d}" if total_count > 1 else ""
        safe_artist = sanitize_filename(track.uploader)
        safe_title = sanitize_filename(track.title)
        
        base_filename = f"{track_num_str} - {safe_artist} - {safe_title}" if total_count > 1 else f"{safe_artist} - {safe_title}"
        base_filename = base_filename.strip(" -")
        download_url = target_url or track.url

        job_temp_dir = settings.TEMP_DIR / job_id
        job_output_dir = settings.OUTPUT_DIR / job_id
        job_temp_dir.mkdir(parents=True, exist_ok=True)
        job_output_dir.mkdir(parents=True, exist_ok=True)

        is_video_mode = any(v in format_val.lower() for v in ["p", "video", "mp4"])

        try:
            # 1. ACQUIRING
            track_progress.status = ItemStatus.ACQUIRING
            track_progress.progress = 15
            track_progress.error = None
            await self.broadcast(job_id)
            logger.info(f"[{track.position}/{total_count}] Step 1/4: Downloading source from {download_url}...")

            raw_download_path = job_temp_dir / f"raw_{track.id}.%(ext)s"
            
            # Format selection string for yt-dlp across platforms
            if is_video_mode:
                if format_val.endswith("p"):
                    height = format_val[:-1]
                    fmt_spec = f"bestvideo[height<={height}]+bestaudio/best[height<={height}]/best"
                else:
                    fmt_spec = "bestvideo+bestaudio/best"
            else:
                fmt_spec = "bestaudio/best"

            cookie_file = get_cookies_filepath()
            ydl_opts = {
                'format': fmt_spec,
                'outtmpl': str(raw_download_path),
                'quiet': True,
                'no_warnings': True,
                'socket_timeout': 45,
                'nocheckcertificate': True,
                'ignoreerrors': False,
                'extractor_args': {
                    'youtube': {
                        'player_client': ['android', 'web']
                    }
                }
            }
            if cookie_file:
                ydl_opts['cookiefile'] = cookie_file
            
            loop = asyncio.get_running_loop()
            await loop.run_in_executor(
                None,
                lambda: yt_dlp.YoutubeDL(ydl_opts).download([download_url])
            )
            
            downloaded_files = list(job_temp_dir.glob(f"raw_{track.id}.*"))
            if not downloaded_files:
                raise RuntimeError("Download completed but input file was not found on disk")
            acquired_file = downloaded_files[0]

            # 2. CONVERTING / MUXING
            track_progress.status = ItemStatus.CONVERTING
            track_progress.progress = 50
            await self.broadcast(job_id)
            
            if is_video_mode:
                logger.info(f"[{track.position}/{total_count}] Step 2/4: Muxing Video MP4 with FFmpeg...")
                converted_file = await converter.convert_and_mux_video(
                    input_path=acquired_file,
                    output_dir=job_output_dir,
                    base_filename=base_filename
                )
            else:
                logger.info(f"[{track.position}/{total_count}] Step 2/4: Encoding Audio {format_val.upper()} with FFmpeg...")
                converted_file = await converter.convert_to_audio(
                    input_path=acquired_file,
                    output_format=format_val,
                    output_dir=job_output_dir,
                    base_filename=base_filename,
                    expected_duration=track.duration if track.duration > 0 else None
                )

            acquired_file.unlink(missing_ok=True)

            # 3. VALIDATING
            track_progress.status = ItemStatus.VALIDATING
            track_progress.progress = 80
            await self.broadcast(job_id)

            # 4. TAGGING (Audio files)
            if not is_video_mode:
                track_progress.status = ItemStatus.TAGGING
                track_progress.progress = 90
                await self.broadcast(job_id)
                await tagger.tag_file(
                    file_path=converted_file,
                    title=track.title,
                    artist=track.uploader,
                    album=playlist_title,
                    track_number=track.position,
                    total_tracks=total_count,
                    cover_url=track.thumbnail
                )

            # 5. COMPLETED
            was_failed = (track_progress.status == ItemStatus.FAILED)
            track_progress.status = ItemStatus.COMPLETED
            track_progress.progress = 100
            track_progress.download_url = f"/api/v1/jobs/{job_id}/files/{converted_file.name}"
            job.completed_tracks += 1
            if was_failed and job.failed_tracks > 0:
                job.failed_tracks -= 1
                
            logger.info(f"[{track.position}/{total_count}] ✓ Finished {track.title}")
            await self.broadcast(job_id)
            return True

        except Exception as e:
            err_clean = str(e).replace('\n', ' ')
            logger.warning(f"[{track.position}/{total_count}] ✕ Failed {track.title}: {err_clean}")
            track_progress.status = ItemStatus.FAILED
            track_progress.error = err_clean
            job.failed_tracks += 1
            await self.broadcast(job_id)
            return False

    async def _process_job(self, job_id: str, req: CreateJobRequest):
        job = self._jobs[job_id]
        job.status = JobStatus.PROCESSING
        await self.broadcast(job_id)

        total_count = len(req.tracks)
        for track in req.tracks:
            await self._execute_single_track(
                job_id=job_id,
                track=track,
                format_val=req.format,
                playlist_title=req.playlist_title,
                total_count=total_count
            )

        self.repackage_zip(job_id)
        job.status = JobStatus.COMPLETED if job.completed_tracks > 0 else JobStatus.FAILED
        logger.info(f"Job [{job_id}] finished. Completed: {job.completed_tracks}, Failed: {job.failed_tracks}")
        await self.broadcast(job_id)

    async def retry_track(self, job_id: str, track_id: str, custom_url: Optional[str] = None):
        job = self._jobs.get(job_id)
        req = self._job_requests.get(job_id)
        if not job or not req:
            raise ValueError("Job not found")

        matching_track = next((t for t in req.tracks if t.id == track_id), None)
        if not matching_track:
            raise ValueError("Track not found")

        if job.tracks[track_id].status == ItemStatus.FAILED and job.failed_tracks > 0:
            job.failed_tracks -= 1

        success = await self._execute_single_track(
            job_id=job_id,
            track=matching_track,
            format_val=job.format,
            playlist_title=job.playlist_title,
            total_count=job.total_tracks,
            target_url=custom_url
        )

        if success:
            self.repackage_zip(job_id)
            job.status = JobStatus.COMPLETED
            await self.broadcast(job_id)

    async def auto_resolve_track(self, job_id: str, track_id: str) -> bool:
        job = self._jobs.get(job_id)
        req = self._job_requests.get(job_id)
        if not job or not req:
            raise ValueError("Job not found")

        matching_track = next((t for t in req.tracks if t.id == track_id), None)
        if not matching_track:
            raise ValueError("Track not found")

        search_query = f"ytsearch1:{matching_track.uploader} - {matching_track.title} audio"
        track_progress = job.tracks[track_id]
        track_progress.status = ItemStatus.ACQUIRING
        track_progress.error = "Searching alternative source..."
        await self.broadcast(job_id)

        try:
            ydl_opts = {'quiet': True, 'no_warnings': True, 'extract_flat': True}
            loop = asyncio.get_running_loop()
            info = await loop.run_in_executor(
                None,
                lambda: yt_dlp.YoutubeDL(ydl_opts).extract_info(search_query, download=False)
            )
            entries = info.get('entries') or []
            if not entries or not entries[0]:
                raise RuntimeError("No alternative audio source found")

            best_match_url = entries[0].get('url') or f"https://www.youtube.com/watch?v={entries[0].get('id')}"
            await self.retry_track(job_id, track_id, custom_url=best_match_url)
            return True
        except Exception as e:
            track_progress.status = ItemStatus.FAILED
            track_progress.error = f"Auto-resolve failed: {str(e)}"
            job.failed_tracks += 1
            await self.broadcast(job_id)
            return False

job_manager = JobManager()
