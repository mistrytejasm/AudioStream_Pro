import asyncio
import logging
from urllib.parse import urlparse
import ipaddress
import socket
from typing import List, Dict, Any, Optional
import yt_dlp

from app.config import settings
from app.models.job import MediaType, MediaAnalysisResult, PlaylistItem, VideoFormatOption

logger = logging.getLogger(__name__)

def is_safe_url(url: str) -> bool:
    try:
        parsed = urlparse(url)
        if parsed.scheme not in ("http", "https"):
            return False
        hostname = parsed.hostname
        if not hostname:
            return False
            
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

def format_bytes(size: Optional[int]) -> Optional[str]:
    if not size:
        return None
    for unit in ['B', 'KB', 'MB', 'GB']:
        if size < 1024.0:
            return f"{size:.1f} {unit}"
        size /= 1024.0
    return f"{size:.1f} TB"

class MediaAnalyzerService:
    @staticmethod
    def _extract_media_sync(url: str) -> MediaAnalysisResult:
        # First test if URL is a playlist or single video
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

            is_playlist = info.get('_type') == 'playlist' or 'entries' in info

            if is_playlist:
                entries = info.get('entries') or []
                items = []
                for idx, entry in enumerate(entries, start=1):
                    if not entry:
                        continue
                    duration = float(entry.get('duration') or 0)
                    item_url = entry.get('url') or entry.get('webpage_url') or f"https://www.youtube.com/watch?v={entry.get('id')}"
                    
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

                return MediaAnalysisResult(
                    type=MediaType.PLAYLIST,
                    id=str(info.get('id') or "playlist"),
                    title=info.get('title') or "Audio Playlist",
                    uploader=info.get('uploader') or info.get('channel') or "Unknown Channel",
                    thumbnail=items[0].thumbnail if items else None,
                    url=url,
                    item_count=len(items),
                    items=items,
                    available_video_formats=[]
                )
            else:
                # Single Video: extract detailed formats
                single_opts = {
                    'skip_download': True,
                    'quiet': True,
                    'no_warnings': True,
                }
                with yt_dlp.YoutubeDL(single_opts) as single_ydl:
                    detailed_info = single_ydl.extract_info(url, download=False)
                    duration = float(detailed_info.get('duration') or 0)
                    
                    thumbnails = detailed_info.get('thumbnails') or []
                    thumbnail_url = detailed_info.get('thumbnail')
                    if thumbnails and isinstance(thumbnails, list):
                        thumbnail_url = thumbnails[-1].get('url', thumbnail_url)

                    # Extract video resolution options
                    formats = detailed_info.get('formats') or []
                    seen_heights = set()
                    video_options = []
                    
                    target_heights = [1080, 720, 480, 360]
                    
                    for target_h in target_heights:
                        # Find matching video streams
                        matching_fmts = [f for f in formats if f.get('height') == target_h and f.get('vcodec') != 'none']
                        if matching_fmts:
                            best_match = matching_fmts[-1]
                            approx_size = best_match.get('filesize') or best_match.get('filesize_approx')
                            video_options.append(VideoFormatOption(
                                format_id=f"{target_h}p",
                                resolution=f"{target_h}p",
                                height=target_h,
                                note="Full HD (MP4)" if target_h == 1080 else ("HD (MP4)" if target_h == 720 else "SD (MP4)"),
                                filesize_approx=format_bytes(approx_size) if approx_size else None
                            ))

                    # If no specific heights found, offer best available
                    if not video_options:
                        video_options.append(VideoFormatOption(
                            format_id="video_best",
                            resolution="Best Video",
                            height=720,
                            note="Highest Available Quality (MP4)"
                        ))

                    single_item = PlaylistItem(
                        id=str(detailed_info.get('id') or "video"),
                        title=str(detailed_info.get('title') or "Video Track"),
                        duration=duration,
                        duration_string=format_duration(duration),
                        uploader=str(detailed_info.get('uploader') or detailed_info.get('channel') or "Unknown Channel"),
                        thumbnail=thumbnail_url,
                        url=url
                    )

                    return MediaAnalysisResult(
                        type=MediaType.SINGLE,
                        id=single_item.id,
                        title=single_item.title,
                        uploader=single_item.uploader,
                        duration=duration,
                        duration_string=format_duration(duration),
                        thumbnail=thumbnail_url,
                        url=url,
                        item_count=1,
                        items=[single_item],
                        available_video_formats=video_options
                    )

    async def analyze_media(self, url: str) -> MediaAnalysisResult:
        if not is_safe_url(url):
            raise ValueError("Invalid or disallowed URL (SSRF protected)")
        return await asyncio.to_thread(self._extract_media_sync, url)

media_analyzer = MediaAnalyzerService()
playlist_service = media_analyzer  # alias for backward compatibility
