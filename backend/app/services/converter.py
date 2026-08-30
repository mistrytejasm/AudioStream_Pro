import logging
import asyncio
from pathlib import Path
from app.config import settings
from app.services.ffmpeg_finder import get_ffmpeg_paths
from app.services.subprocess_runner import run_sync_cmd
from app.services.validator import validator, MediaValidationError

logger = logging.getLogger(__name__)

class MediaConversionError(Exception):
    pass

class MediaConverter:
    def __init__(self):
        self.ffmpeg_path, _ = get_ffmpeg_paths()

    async def convert_to_audio(
        self,
        input_path: Path,
        output_format: str,
        output_dir: Path,
        base_filename: str,
        expected_duration: float = None
    ) -> Path:
        output_format = output_format.lower()
        if output_format in ("m4a", "aac", "m4a_aac"):
            ext = "m4a"
            output_file = output_dir / f"{base_filename}.{ext}"
            cmd = [
                self.ffmpeg_path,
                "-y",
                "-i", str(input_path),
                "-vn", "-sn",
                "-c:a", "aac",
                "-b:a", settings.M4A_BITRATE,
                "-ar", settings.AUDIO_SAMPLE_RATE,
                "-ac", "2",
                "-movflags", "+faststart",
                "-map_metadata", "-1",
                str(output_file)
            ]
        elif output_format == "mp3":
            ext = "mp3"
            output_file = output_dir / f"{base_filename}.{ext}"
            cmd = [
                self.ffmpeg_path,
                "-y",
                "-i", str(input_path),
                "-vn", "-sn",
                "-c:a", "libmp3lame",
                "-b:a", settings.MP3_BITRATE,
                "-ar", settings.AUDIO_SAMPLE_RATE,
                "-ac", "2",
                "-map_metadata", "-1",
                str(output_file)
            ]
        else:
            raise MediaConversionError(f"Unsupported audio format: {output_format}")

        logger.info(f"Running FFmpeg audio conversion for {input_path.name} -> {output_file.name}")
        
        loop = asyncio.get_running_loop()
        ret_code, stdout, stderr = await loop.run_in_executor(
            None,
            lambda: run_sync_cmd(cmd, timeout=settings.FFMPEG_TIMEOUT_SECONDS)
        )

        if ret_code != 0:
            raise MediaConversionError(f"FFmpeg audio error (code {ret_code}): {stderr}")

        # Strict validation
        try:
            logger.info(f"Validating converted audio {output_file.name}...")
            await validator.validate_output_audio(
                file_path=output_file,
                expected_format=output_format,
                expected_duration=expected_duration
            )
            logger.info(f"✓ Validation passed for {output_file.name}")
        except MediaValidationError as e:
            if output_file.exists():
                output_file.unlink(missing_ok=True)
            raise MediaConversionError(f"Output validation failed: {e}")

        return output_file

    async def convert_and_mux_video(
        self,
        input_path: Path,
        output_dir: Path,
        base_filename: str
    ) -> Path:
        output_file = output_dir / f"{base_filename}.mp4"
        
        # Mux to universal H.264 + AAC MP4 with faststart
        cmd = [
            self.ffmpeg_path,
            "-y",
            "-i", str(input_path),
            "-c:v", "copy",
            "-c:a", "aac",
            "-b:a", "192k",
            "-movflags", "+faststart",
            str(output_file)
        ]

        logger.info(f"Running FFmpeg video muxing for {input_path.name} -> {output_file.name}")
        
        loop = asyncio.get_running_loop()
        ret_code, stdout, stderr = await loop.run_in_executor(
            None,
            lambda: run_sync_cmd(cmd, timeout=settings.FFMPEG_TIMEOUT_SECONDS)
        )

        # Fallback if stream copy fails
        if ret_code != 0:
            logger.warning("Fast stream-copy failed, falling back to full re-encode...")
            fallback_cmd = [
                self.ffmpeg_path,
                "-y",
                "-i", str(input_path),
                "-c:v", "libx264",
                "-preset", "fast",
                "-crf", "22",
                "-c:a", "aac",
                "-b:a", "192k",
                "-movflags", "+faststart",
                str(output_file)
            ]
            ret_code, stdout, stderr = await loop.run_in_executor(
                None,
                lambda: run_sync_cmd(fallback_cmd, timeout=settings.FFMPEG_TIMEOUT_SECONDS)
            )

        if ret_code != 0 or not output_file.exists() or output_file.stat().st_size < 10240:
            raise MediaConversionError(f"FFmpeg video conversion failed: {stderr}")

        return output_file

converter = MediaConverter()
