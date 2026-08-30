import asyncio
import logging
from urllib.parse import urlparse
import ipaddress
import socket
from typing import List, Dict, Any, Optional
import yt_dlp
from pydantic import BaseModel
from app.config import settings

logger = logging.getLogger(__name__)

class PlaylistItem(BaseModel):
    id: str
    title: str
    duration: float
    duration_string: str
    uploader: str
    thumbnail: Optional[str] = None
    url: str

class PlaylistMetadata(BaseModel):
    id: str
    title: str
    uploader: str
    item_count: int
    items: List[PlaylistItem]

def is_safe_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False
            
        # Disallow loopback / private IP SSRF
        ip = socket.gethostbyname(hostname)
        ip_obj = ipaddress.ip_address(ip)
        if ip_obj.is_private or ip_obj.is_loopback or ip_obj.is_reserved:
            return False
            
        return True
    except Exception:
        return False

def format_duration(seconds: Optional[float]) -> str:
    if not seconds or seconds < 0:
        return "0:00"
    m, s = divmod(int(seconds), 60)
    h, m = divmod(m, 60)
    if h > 0:
        return f"{h}:{m:02d}:{s:02d}"
    return f"{m}:{s:02d}"

class PlaylistService:
    @staticmethod
    def _extract_playlist_sync(url: str) -> PlaylistMetadata:
        ydl_opts = {
            'extract_flat': 'in_playlist',
            'skip_download': True,
            'quiet': True,
            'no_warnings': True,
            'playlistend': settings.MAX_PLAYLIST_ITEMS,
        }
        
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                raise ValueError("Could not extract metadata from provided URL")
                
            entries = info.get('entries') or [info]
            items = []
            
            for idx, entry in enumerate(entries, start=1):
                if not entry:
                    continue
                duration = float(entry.get('duration') or 0)
                item_url = entry.get('url') or entry.get('webpage_url') or f"https://www.youtube.com/watch?v={entry.get('id')}"
                
                # Fetch highest quality thumbnail
                thumbnails = entry.get('thumbnails') or []
                thumbnail_url = entry.get('thumbnail')
                if thumbnails and isinstance(thumbnails, list):
                    thumbnail_url = thumbnails[-1].get('url', thumbnail_url)
                
                items.append(PlaylistItem(
                    id=str(entry.get('id') or f"track_{idx}"),
                    title=str(entry.get('title') or f"Track {idx}"),
                    duration=duration,
                    duration_string=format_duration(duration),
                    uploader=str(entry.get('uploader') or entry.get('channel') or "Unknown Artist"),
                    thumbnail=thumbnail_url,
                    url=item_url
                ))

            playlist_title = info.get('title') or "Audio Playlist"
            uploader = info.get('uploader') or info.get('channel') or "Unknown Channel"
            
            return PlaylistMetadata(
                id=str(info.get('id') or "playlist"),
                title=playlist_title,
                uploader=uploader,
                item_count=len(items),
                items=items
            )

    async def analyze_playlist(self, url: str) -> PlaylistMetadata:
        if not is_safe_url(url):
            raise ValueError("Invalid or disallowed URL (SSRF protected)")
        return await asyncio.to_thread(self._extract_playlist_sync, url)

playlist_service = PlaylistService()
