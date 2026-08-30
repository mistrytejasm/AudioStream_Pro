from pathlib import Path
from typing import Optional
from pydantic_settings import BaseSettings
from pydantic import ConfigDict

class Settings(BaseSettings):
    model_config = ConfigDict(case_sensitive=True, extra="ignore")

    PROJECT_NAME: str = "Playlist Audio Converter"
    API_V1_STR: str = "/api/v1"
    
    BASE_DIR: Path = Path(__file__).resolve().parent.parent.parent
    STORAGE_DIR: Path = BASE_DIR / "storage"
    TEMP_DIR: Path = STORAGE_DIR / "temp"
    OUTPUT_DIR: Path = STORAGE_DIR / "output"
    
    MAX_PLAYLIST_ITEMS: int = 100
    FFMPEG_TIMEOUT_SECONDS: int = 600
    DOWNLOAD_TIMEOUT_SECONDS: int = 600
    
    MP3_BITRATE: str = "320k"
    M4A_BITRATE: str = "256k"
    AUDIO_SAMPLE_RATE: str = "44100"

    # Optional YouTube authentication/cookies for cloud servers
    YOUTUBE_COOKIES: Optional[str] = None
    YOUTUBE_COOKIES_FILE: Optional[str] = None
    COOKIES_TXT_PATH: Path = BASE_DIR / "cookies.txt"

settings = Settings()
settings.TEMP_DIR.mkdir(parents=True, exist_ok=True)
settings.OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
