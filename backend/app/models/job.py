from enum import Enum
from typing import List, Optional, Dict, Any
from pydantic import BaseModel, Field

class OutputFormat(str, Enum):
    MP3 = "mp3"
    M4A = "m4a"

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
    playlist_id: str
    playlist_title: str
    format: OutputFormat = OutputFormat.M4A
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
    playlist_title: str
    format: OutputFormat
    status: JobStatus
    total_tracks: int
    completed_tracks: int = 0
    failed_tracks: int = 0
    tracks: Dict[str, TrackProgress] = Field(default_factory=dict)
    zip_download_url: Optional[str] = None
    error: Optional[str] = None
