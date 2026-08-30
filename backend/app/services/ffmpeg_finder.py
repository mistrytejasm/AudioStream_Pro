import shutil
import logging
from pathlib import Path
import static_ffmpeg

logger = logging.getLogger(__name__)

def get_ffmpeg_paths() -> tuple[str, str]:
    # Check system PATH first
    ffmpeg_bin = shutil.which("ffmpeg")
    ffprobe_bin = shutil.which("ffprobe")
    
    if not ffmpeg_bin or not ffprobe_bin:
        try:
            static_ffmpeg.add_paths()
            ffmpeg_bin = shutil.which("ffmpeg")
            ffprobe_bin = shutil.which("ffprobe")
        except Exception as e:
            logger.warning(f"static_ffmpeg add_paths failed: {e}")
            
    if not ffmpeg_bin or not ffprobe_bin:
        raise RuntimeError("Neither system ffmpeg/ffprobe nor static_ffmpeg could be located.")
        
    return str(ffmpeg_bin), str(ffprobe_bin)
