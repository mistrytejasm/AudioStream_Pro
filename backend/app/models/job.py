from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class Platform(str, Enum):
    YOUTUBE = "youtube"
    INSTAGRAM = "instagram"
    TWITTER = "twitter"
    FACEBOOK = "facebook"
    GENERIC = "generic"

class MediaType(str, Enum):
    SINGLE = "single"
    PLAYLIST = "playlist"

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

class QualityOption(BaseModel):
    format_id: str
    label: str
    resolution: str
    ext: str = "mp4"
    filesize_approx: Optional[str] = None
    type: str = "video_audio"  # "video_audio" or "audio_only"
    note: str = ""

class PlaylistItem(BaseModel):
    id: str
    title: str
    duration: float
    duration_string: str
    uploader: str
    thumbnail: Optional[str] = None
    url: str

class MediaAnalysisResult(BaseModel):
    platform: Platform = Platform.GENERIC
    type: MediaType = MediaType.SINGLE
    id: str
    title: str
    uploader: str
    duration: Optional[float] = None
    duration_string: Optional[str] = None
    thumbnail: Optional[str] = None
    url: str
    item_count: int = 1
    items: List[PlaylistItem] = Field(default_factory=list)
    quality_options: List[QualityOption] = Field(default_factory=list)

class AnalyzeRequest(BaseModel):
    url: str
    platform_hint: Optional[str] = None

class TrackSelection(BaseModel):
    id: str
    title: str
    url: str
    duration: float
    uploader: str
    thumbnail: Optional[str] = None
    position: int

class CreateJobRequest(BaseModel):
    platform: Platform = Platform.GENERIC
    media_type: MediaType = MediaType.SINGLE
    playlist_id: str
    playlist_title: str
    format: str = "m4a"  # 1080p, 720p, 480p, 360p, m4a, mp3, etc.
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
    platform: Platform = Platform.GENERIC
    media_type: MediaType = MediaType.SINGLE
    playlist_title: str
    format: str
    status: JobStatus
    total_tracks: int
    completed_tracks: int = 0
    failed_tracks: int = 0
    tracks: Dict[str, TrackProgress] = Field(default_factory=dict)
    zip_download_url: Optional[str] = None
    error: Optional[str] = None
