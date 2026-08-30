import io
import re
import logging
import httpx
from pathlib import Path
from typing import Optional
from PIL import Image
import mutagen
from mutagen.mp3 import MP3
from mutagen.id3 import ID3, TIT2, TPE1, TPE2, TALB, TRCK, TDRC, TCON, APIC, ID3NoHeaderError
from mutagen.mp4 import MP4, MP4Cover

logger = logging.getLogger(__name__)

def sanitize_string(val: Optional[str], default: str = "") -> str:
    if not val:
        return default
    # Strip invalid / dangerous control chars
    clean = re.sub(r'[\r\n\t\x00-\x1f]', ' ', val).strip()
    return clean or default

def sanitize_filename(name: str) -> str:
    cleaned = re.sub(r'[\\/*?:"<>|]', '_', name)
    cleaned = re.sub(r'\s+', ' ', cleaned).strip()
    return cleaned[:120] if cleaned else "track"

class MetadataTagger:
    @staticmethod
    async def fetch_cover_art(image_url: Optional[str]) -> Optional[bytes]:
        if not image_url:
            return None
        try:
            async with httpx.AsyncClient(timeout=15.0, follow_redirects=True) as client:
                res = await client.get(image_url)
                if res.status_code == 200:
                    img_data = res.content
                    # Process image to square JPEG, max 800x800
                    with Image.open(io.BytesIO(img_data)) as img:
                        img = img.convert("RGB")
                        # Center crop square
                        width, height = img.size
                        min_dim = min(width, height)
                        left = (width - min_dim) // 2
                        top = (height - min_dim) // 2
                        img = img.crop((left, top, left + min_dim, top + min_dim))
                        img.thumbnail((800, 800), Image.Resampling.LANCZOS)
                        
                        out_buf = io.BytesIO()
                        img.save(out_buf, format="JPEG", quality=90)
                        return out_buf.getvalue()
        except Exception as e:
            logger.warning(f"Could not fetch or process cover art from {image_url}: {e}")
        return None

    @classmethod
    async def tag_file(
        cls,
        file_path: Path,
        title: str,
        artist: str,
        album: str,
        track_number: int,
        total_tracks: int,
        year: Optional[str] = None,
        genre: Optional[str] = None,
        cover_url: Optional[str] = None
    ) -> bool:
        title = sanitize_string(title, "Unknown Title")
        artist = sanitize_string(artist, "Unknown Artist")
        album = sanitize_string(album, "Unknown Album")
        genre = sanitize_string(genre, "Audio")
        year = sanitize_string(year, "")
        
        cover_bytes = await cls.fetch_cover_art(cover_url)
        ext = file_path.suffix.lower()

        if ext == ".mp3":
            try:
                try:
                    audio = ID3(str(file_path))
                except ID3NoHeaderError:
                    audio = ID3()
                
                audio.add(TIT2(encoding=3, text=title))
                audio.add(TPE1(encoding=3, text=artist))
                audio.add(TPE2(encoding=3, text=artist))
                audio.add(TALB(encoding=3, text=album))
                audio.add(TRCK(encoding=3, text=f"{track_number}/{total_tracks}"))
                if year:
                    audio.add(TDRC(encoding=3, text=year))
                if genre:
                    audio.add(TCON(encoding=3, text=genre))
                    
                if cover_bytes:
                    audio.add(APIC(
                        encoding=3,
                        mime="image/jpeg",
                        type=3,  # Front cover
                        desc="Cover",
                        data=cover_bytes
                    ))
                audio.save(str(file_path), v2_version=4)
                return True
            except Exception as e:
                logger.error(f"Error tagging MP3 file {file_path.name}: {e}")
                return False

        elif ext == ".m4a":
            try:
                mp4 = MP4(str(file_path))
                mp4["\xa9nam"] = [title]
                mp4["\xa9ART"] = [artist]
                mp4["aART"] = [artist]
                mp4["\xa9alb"] = [album]
                mp4["trkn"] = [(track_number, total_tracks)]
                if year:
                    mp4["\xa9day"] = [year]
                if genre:
                    mp4["\xa9gen"] = [genre]
                if cover_bytes:
                    mp4["covr"] = [MP4Cover(cover_bytes, imageformat=MP4Cover.FORMAT_JPEG)]
                mp4.save()
                return True
            except Exception as e:
                logger.error(f"Error tagging M4A file {file_path.name}: {e}")
                return False

        return False

tagger = MetadataTagger()
