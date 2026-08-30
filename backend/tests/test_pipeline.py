import pytest
import asyncio
from pathlib import Path
from app.services.ffmpeg_finder import get_ffmpeg_paths
from app.services.converter import converter
from app.services.validator import validator, MediaValidationError
from app.services.tagger import tagger
from app.config import settings

@pytest.mark.asyncio
async def test_ffmpeg_paths():
    ffmpeg, ffprobe = get_ffmpeg_paths()
    assert Path(ffmpeg).exists()
    assert Path(ffprobe).exists()

@pytest.mark.asyncio
async def test_audio_conversion_and_validation():
    ffmpeg, _ = get_ffmpeg_paths()
    test_dir = settings.TEMP_DIR / "test_run"
    test_dir.mkdir(parents=True, exist_ok=True)
    
    # 1. Generate 3-second synthetic sine audio wave
    input_wav = test_dir / "sine_input.wav"
    cmd = [
        ffmpeg, "-y",
        "-f", "lavfi", "-i", "sine=frequency=440:duration=3",
        str(input_wav)
    ]
    proc = await asyncio.create_subprocess_exec(*cmd)
    await proc.communicate()
    assert input_wav.exists()
    assert input_wav.stat().st_size > 1024

    # 2. Test M4A/AAC conversion
    output_m4a = await converter.convert_to_audio(
        input_path=input_wav,
        output_format="m4a",
        output_dir=test_dir,
        base_filename="test_track_m4a",
        expected_duration=3.0
    )
    assert output_m4a.exists()
    
    # Tag M4A
    tagged_m4a = await tagger.tag_file(
        file_path=output_m4a,
        title="Test Song M4A",
        artist="Test Artist",
        album="Test Album",
        track_number=1,
        total_tracks=1,
        year="2024",
        genre="Test"
    )
    assert tagged_m4a is True
    
    # 3. Test MP3 conversion
    output_mp3 = await converter.convert_to_audio(
        input_path=input_wav,
        output_format="mp3",
        output_dir=test_dir,
        base_filename="test_track_mp3",
        expected_duration=3.0
    )
    assert output_mp3.exists()
    
    # Tag MP3
    tagged_mp3 = await tagger.tag_file(
        file_path=output_mp3,
        title="Test Song MP3",
        artist="Test Artist",
        album="Test Album",
        track_number=1,
        total_tracks=1,
        year="2024",
        genre="Test"
    )
    assert tagged_mp3 is True

    # 4. Test corruption detection
    corrupt_file = test_dir / "corrupt.mp3"
    corrupt_file.write_bytes(b"invalid garbage byte header")
    with pytest.raises(MediaValidationError):
        await validator.validate_output_audio(corrupt_file, "mp3")

    # Cleanup
    for f in test_dir.iterdir():
        f.unlink(missing_ok=True)
    test_dir.rmdir()
