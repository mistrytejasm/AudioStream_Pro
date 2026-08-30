from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class MediaType(str, Enum):
    SINGLE = "single"
    PLAYLIST = "playlist"

class OutputFormat(str, Enum):
    MP3 = "mp3"
    M4A = "m4a"
    VIDEO_1080P = "1080p"
    VIDEO_720P = "720p"
    VIDEO_480P = "480p"
    VIDEO_360P = "360p"
    VIDEO_BEST = "video_best"

class ItemStatus(str, Enum):
    PENDING = "PENDING"
    ACQUIRING = "ACQUIRING"
    CONVERTING = "CONVERTING"
    VALIDATING = "VALIDATING"
    TAGGING = "TAGGING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class JobStatus(str, Enum):
    QUEUED = "QUEUED"
    PROCESSING = "PROCESSING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"

class VideoFormatOption(BaseModel):
    format_id: str
    resolution: str
    height: int
    note: str
    filesize_approx: Optional[str] = None
    ext: str = "mp4"

class PlaylistItem(BaseModel):
    id: str
    title: str
    duration: float
    duration_string: str
    uploader: str
    thumbnail: Optional[str] = None
    url: str

class MediaAnalysisResult(BaseModel):
    type: MediaType
    id: str
    title: str
    uploader: str
    duration: Optional[float] = None
    duration_string: Optional[str] = None
    thumbnail: Optional[str] = None
    url: str
    item_count: int = 1
    items: List[PlaylistItem] = Field(default_factory=list)
    available_video_formats: List[VideoFormatOption] = Field(default_factory=list)

class AnalyzeRequest(BaseModel):
    url: str

class TrackSelection(BaseModel):
    id: str
    title: str
    url: str
    duration: float
    uploader: str
    thumbnail: Optional[str] = None
    position: int

class CreateJobRequest(BaseModel):
    media_type: MediaType = MediaType.PLAYLIST
    playlist_id: str
    playlist_title: str
    format: str = "m4a"  # can be m4a, mp3, 1080p, 720p, 480p, 360p, video_best
    tracks: List[TrackSelection]

class TrackProgress(BaseModel):
    id: str
    title: str
    position: int
    status: ItemStatus
    progress: int = 0
    error: Optional[str] = None
    download_url: Optional[str] = None

class JobState(BaseModel):
    job_id: str
    media_type: MediaType = MediaType.PLAYLIST
    playlist_title: str
    format: str
    status: JobStatus
    total_tracks: int
    completed_tracks: int = 0
    failed_tracks: int = 0
    tracks: Dict[str, TrackProgress] = Field(default_factory=dict)
    zip_download_url: Optional[str] = None
    error: Optional[str] = None
