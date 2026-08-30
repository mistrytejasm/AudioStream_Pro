import json
import logging
import asyncio
from pathlib import Path
from typing import Dict, Any, Optional
from app.services.ffmpeg_finder import get_ffmpeg_paths
from app.services.subprocess_runner import run_sync_cmd

logger = logging.getLogger(__name__)

class MediaValidationError(Exception):
    pass

class MediaValidator:
    def __init__(self):
        _, self.ffprobe_path = get_ffmpeg_paths()
        self.ffmpeg_path, _ = get_ffmpeg_paths()

    async def probe(self, file_path: Path) -> Dict[str, Any]:
        if not file_path.exists():
            raise MediaValidationError(f"File not found: {file_path}")
            
        cmd = [
            self.ffprobe_path,
            "-v", "error",
            "-show_entries", "format=duration,format_name,size:stream=codec_name,codec_type,channels,sample_rate,bit_rate",
            "-of", "json",
            str(file_path)
        ]
        
        loop = asyncio.get_running_loop()
        ret_code, stdout, stderr = await loop.run_in_executor(None, lambda: run_sync_cmd(cmd, timeout=60))
        
        if ret_code != 0:
            raise MediaValidationError(f"ffprobe failed (code {ret_code}): {stderr}")
            
        try:
            return json.loads(stdout)
        except Exception as e:
            raise MediaValidationError(f"Failed to parse ffprobe json output: {e}")

    async def validate_output_audio(
        self, 
        file_path: Path, 
        expected_format: str, 
        expected_duration: Optional[float] = None
    ) -> bool:
        # 1. Size Check (> 1024 bytes)
        if not file_path.exists() or file_path.stat().st_size < 1024:
            raise MediaValidationError(f"File {file_path.name} is missing or too small (<1KB). Size: {file_path.stat().st_size if file_path.exists() else 0} bytes")

        # 2. Probe stream & format
        data = await self.probe(file_path)
        streams = data.get("streams", [])
        fmt = data.get("format", {})
        
        audio_streams = [s for s in streams if s.get("codec_type") == "audio"]
        if not audio_streams:
            raise MediaValidationError(f"No audio stream found in {file_path.name}")

        audio = audio_streams[0]
        codec_name = audio.get("codec_name", "").lower()
        format_name = fmt.get("format_name", "").lower()

        # 3. Format/Codec compliance
        if expected_format.lower() == "mp3":
            if "mp3" not in codec_name:
                raise MediaValidationError(f"Expected MP3 codec, got {codec_name}")
        elif expected_format.lower() in ("m4a", "aac", "m4a_aac"):
            if codec_name != "aac":
                raise MediaValidationError(f"Expected AAC codec in M4A, got {codec_name}")
            if not any(f in format_name for f in ["mov", "mp4", "m4a"]):
                raise MediaValidationError(f"Expected MP4/M4A container, got {format_name}")
        else:
            raise MediaValidationError(f"Unsupported format: {expected_format}")

        # 4. Duration Check
        actual_duration = float(fmt.get("duration", 0))
        if actual_duration <= 0:
            raise MediaValidationError(f"Invalid duration: {actual_duration}s")
            
        if expected_duration and expected_duration > 0:
            diff = abs(actual_duration - expected_duration)
            tolerance = max(3.0, expected_duration * 0.05) # 5% or 3s tolerance
            if diff > tolerance:
                raise MediaValidationError(f"Duration mismatch: expected ~{expected_duration}s, got {actual_duration}s (diff {diff:.2f}s > tolerance {tolerance:.2f}s)")

        # 5. Null Decode Integrity Pass
        decode_cmd = [
            self.ffmpeg_path,
            "-v", "error",
            "-i", str(file_path),
            "-f", "null",
            "-"
        ]
        loop = asyncio.get_running_loop()
        ret_code, _, stderr = await loop.run_in_executor(None, lambda: run_sync_cmd(decode_cmd, timeout=120))
        
        if ret_code != 0:
            raise MediaValidationError(f"Null decode pass failed for {file_path.name}: {stderr}")

        return True

validator = MediaValidator()
