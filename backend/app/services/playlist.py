import asyncio
import logging
from urllib.parse import urlparse
import ipaddress
import socket
from typing import List, Dict, Any, Optional
import yt_dlp

from app.config import settings
from app.models.job import Platform, MediaType, MediaAnalysisResult, PlaylistItem, QualityOption

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

def detect_platform(url: str) -> Platform:
    u = url.lower()
    if any(d in u for d in ["youtube.com", "youtu.be"]):
        return Platform.YOUTUBE
    if any(d in u for d in ["instagram.com", "instagr.am"]):
        return Platform.INSTAGRAM
    if any(d in u for d in ["twitter.com", "x.com", "t.co"]):
        return Platform.TWITTER
    if any(d in u for d in ["facebook.com", "fb.watch", "fb.com", "fb.me"]):
        return Platform.FACEBOOK
    return Platform.GENERIC

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

class MultiPlatformAnalyzerService:
    @staticmethod
    def _extract_media_sync(url: str) -> MediaAnalysisResult:
        platform = detect_platform(url)

        ydl_opts = {
            'extract_flat': 'in_playlist' if platform == Platform.YOUTUBE else False,
            'skip_download': True,
            'quiet': True,
            'no_warnings': True,
            'playlistend': settings.MAX_PLAYLIST_ITEMS,
            'nocheckcertificate': True,
        }

        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                raise ValueError(f"Could not extract information from {platform.value.upper()} URL")

            is_playlist = (info.get('_type') == 'playlist' or 'entries' in info) and len(info.get('entries', [])) > 1

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
                    platform=platform,
                    type=MediaType.PLAYLIST,
                    id=str(info.get('id') or "playlist"),
                    title=info.get('title') or "Media Playlist",
                    uploader=info.get('uploader') or info.get('channel') or "Unknown Channel",
                    thumbnail=items[0].thumbnail if items else None,
                    url=url,
                    item_count=len(items),
                    items=items,
                    quality_options=[]
                )
            else:
                # Single Media (YouTube, Instagram, Twitter/X, Facebook)
                # If entries list has 1 item, flatten it
                if 'entries' in info and info['entries']:
                    info = info['entries'][0]

                duration = float(info.get('duration') or 0)
                thumbnails = info.get('thumbnails') or []
                thumbnail_url = info.get('thumbnail')
                if thumbnails and isinstance(thumbnails, list):
                    thumbnail_url = thumbnails[-1].get('url', thumbnail_url)

                title = info.get('title') or f"{platform.value.capitalize()} Video"
                uploader = info.get('uploader') or info.get('channel') or info.get('uploader_id') or f"@{platform.value}"

                formats = info.get('formats') or []
                quality_options: List[QualityOption] = []

                # Find video formats
                target_resolutions = [
                    (1080, "1080p Full HD", "Best Visual Quality"),
                    (720, "720p HD", "Standard HD Video"),
                    (480, "480p SD", "Efficient Compact Video"),
                    (360, "360p", "Small File Size")
                ]

                has_specific_resolutions = False
                for height, label, note in target_resolutions:
                    matching_fmts = [f for f in formats if f.get('height') == height and f.get('vcodec') != 'none']
                    if matching_fmts:
                        has_specific_resolutions = True
                        best_match = matching_fmts[-1]
                        approx_size = best_match.get('filesize') or best_match.get('filesize_approx')
                        quality_options.append(QualityOption(
                            format_id=f"{height}p",
                            label=label,
                            resolution=f"{height}p",
                            ext="mp4",
                            filesize_approx=format_bytes(approx_size) if approx_size else None,
                            type="video_audio",
                            note=note
                        ))

                # For platforms without discrete DASH heights (e.g. direct Instagram/Twitter/Facebook streams)
                if not has_specific_resolutions:
                    approx_size = info.get('filesize') or info.get('filesize_approx')
                    quality_options.append(QualityOption(
                        format_id="video_best",
                        label="Best Video (MP4)",
                        resolution="Original Quality",
                        ext="mp4",
                        filesize_approx=format_bytes(approx_size) if approx_size else None,
                        type="video_audio",
                        note="Highest Available Stream"
                    ))

                # Add Audio Options
                quality_options.append(QualityOption(
                    format_id="m4a",
                    label="M4A (AAC 256 kbps)",
                    resolution="Audio (Apple / iPhone)",
                    ext="m4a",
                    type="audio_only",
                    note="High Fidelity AAC with Tags"
                ))
                quality_options.append(QualityOption(
                    format_id="mp3",
                    label="MP3 (320 kbps CBR)",
                    resolution="Audio (Universal)",
                    ext="mp3",
                    type="audio_only",
                    note="Maximum Quality MP3 with ID3v2.4"
                ))

                single_item = PlaylistItem(
                    id=str(info.get('id') or "single_media"),
                    title=title,
                    duration=duration,
                    duration_string=format_duration(duration),
                    uploader=uploader,
                    thumbnail=thumbnail_url,
                    url=url
                )

                return MediaAnalysisResult(
                    platform=platform,
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
                    quality_options=quality_options
                )

    async def analyze_media(self, url: str) -> MediaAnalysisResult:
        if not is_safe_url(url):
            raise ValueError("Invalid or disallowed URL (SSRF protected)")
        return await asyncio.to_thread(self._extract_media_sync, url)

media_analyzer = MultiPlatformAnalyzerService()
playlist_service = media_analyzer
