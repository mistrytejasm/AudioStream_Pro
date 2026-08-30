# AudioStream Pro — Universal Multi-Platform Media & Playlist Downloader

**AudioStream Pro** is a high-performance, production-grade media downloader and conversion engine built with **FastAPI**, **FFmpeg**, and **yt-dlp**. It supports downloading high-definition videos (up to **4K Ultra HD** and **2K QHD**) and high-fidelity audio (**Apple-optimized M4A** & **MP3 320k CBR**) across **YouTube**, **Instagram**, **X (Twitter)**, and **Facebook**, complete with real-time SSE progress streaming and batch ZIP packaging.

---

## 🚀 Key Features

### 1. 🌐 Multi-Platform Support
- **YouTube:** Single videos, Shorts, Music videos, and complete playlists up to 4K/8K.
- **Instagram:** Reels, video posts, and carousel media.
- **X (Twitter):** High-bitrate video clips and audio streams.
- **Facebook:** Watch videos, public reels, and high-definition streams.
- **Smart Auto-Detection:** Automatically detects the platform domain from any pasted URL with SSRF protection.

### 2. 🎬 Dynamic Video Resolution Ladder (Up to 4K & 2K)
Dynamically scans all available stream tracks from the provider:
- **8K / 4K Ultra HD (`2160p` / `60fps HDR`)** — Ultra High Definition
- **2K Quad HD (`1440p` / `60fps`)** — Quad HD visual clarity
- **1080p Full HD (`1080p` / `60fps`)** — FHD crisp playback
- **720p HD**, **480p SD**, **360p**, **240p**, **144p**
- Automated DASH video + audio stream muxing using FFmpeg with `-movflags +faststart` for instant web streaming.

### 3. 🎵 High-Fidelity Audio Conversion Pipeline
- **M4A (AAC 256 kbps):** Optimized with iTunes atoms (`covr`, `©nam`, `©ART`, `©alb`) and `+faststart` atom placement for native Apple Music / iPhone sync.
- **MP3 (320 kbps CBR):** Pure constant bitrate encoding (`libmp3lame`) with ID3v2.4 frames (`TIT2`, `TPE1`, `TALB`, `TRCK`, `APIC`).
- **Cover Artwork:** Automatic square-cropped high-resolution cover extraction embedded directly into the files.

### 4. 🛡️ Strict Anti-Corruption & Quality Validation Engine
Every converted file undergoes a multi-stage validation before being marked ready:
1. **Size Integrity:** Guard checks against empty files (>1024 bytes).
2. **`ffprobe` JSON Stream Inspection:** Verifies audio/video stream presence, codec compliance, and sample rate (44.1/48kHz).
3. **Duration Tolerance Validation:** Confirms converted file duration matches expected source duration within $\le 3\%$.
4. **Null-Decode Integrity Pass:** Runs `ffmpeg -v error -i <file> -f null -` to verify 0 decoding errors or corrupt frame drops.

### 5. ⚡ Smart Error Recovery & Auto-Resolve
- **Instant Track Retry:** One-click retry for transient network hiccups.
- **AI Auto-Resolve:** Automatically searches for working high-quality audio alternatives when regional/bot restrictions block a YouTube track.
- **Custom URL Substitution:** Paste an alternative working link to replace an unavailable video without restarting the whole batch.
- **Automatic ZIP Repackaging:** Seamlessly updates the final playlist archive whenever a recovered track completes.

---

## 🛠️ Technology Stack

| Layer | Technology |
| :--- | :--- |
| **Backend Framework** | [FastAPI](https://fastapi.tiangolo.com/) (Python 3.12, AsyncIO) |
| **Media Processing** | [FFmpeg](https://ffmpeg.org/) & [FFprobe](https://ffmpeg.org/ffprobe.html) (via `static-ffmpeg` fallback) |
| **Stream Extraction** | [yt-dlp](https://github.com/yt-dlp/yt-dlp) |
| **Tagging & Metadata** | [Mutagen](https://mutagen.readthedocs.io/) (ID3 & MP4 Atoms) |
| **Frontend** | Vanilla JS + Tailwind CSS (No heavy framework, zero build step) |
| **Real-Time Updates** | Server-Sent Events (SSE) Streaming |
| **Testing** | Pytest + Pytest-AsyncIO |

---

## 📂 Project Architecture

```
youtube_playlist_download/
├── backend/
│   ├── app/
│   │   ├── config.py              # Central Pydantic Settings & storage paths
│   │   ├── main.py                # FastAPI app initialization & static mounts
│   │   ├── models/
│   │   │   └── job.py             # Pydantic schemas (Platforms, Jobs, Quality Options)
│   │   ├── routes/
│   │   │   └── api.py             # REST endpoints & SSE streaming routes
│   │   ├── services/
│   │   │   ├── ffmpeg_finder.py   # System FFmpeg/FFprobe binary detection
│   │   │   ├── subprocess_runner.py # Threadpool Windows-safe async process runner
│   │   │   ├── validator.py       # Multi-point media integrity verifier
│   │   │   ├── converter.py       # FFmpeg audio conversion & 4K/2K/HD video muxing
│   │   │   ├── tagger.py          # ID3v2.4 & iTunes metadata/artwork embedder
│   │   │   ├── packager.py        # Streaming ZIP packager
│   │   │   ├── playlist.py        # Multi-platform URL & stream analyzer
│   │   │   └── job_manager.py     # State machine, queue, and SSE broadcaster
│   │   └── static/
│   │       └── index.html         # Responsive, dark-mode Web UI
│   └── tests/
│       ├── test_pipeline.py       # Audio/Video conversion & validation tests
│       └── test_multi_platform.py # Multi-platform URL parser tests
├── storage/
│   ├── temp/                      # Temporary working directory for raw streams
│   └── output/                    # Converted MP4, M4A, MP3, and ZIP downloads
├── requirements.txt               # Python package dependencies
└── README.md                      # Project documentation
```

---

## 🏃 Quick Start Guide

### Prerequisites
- **Python 3.10+** (Tested on Python 3.12)
- **FFmpeg** (Recommended: installed on system `PATH` or will automatically use `static-ffmpeg`)

### 1. Setup Virtual Environment & Dependencies
```powershell
# Navigate to the backend directory
cd backend

# Create virtual environment
python -m venv .venv

# Activate virtual environment
# Windows PowerShell:
.\.venv\Scripts\Activate.ps1
# Linux/macOS:
# source .venv/bin/activate

# Install dependencies
pip install -r ../requirements.txt
```

### 2. Launch the Application
```powershell
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```

### 3. Open in Browser
Open **`http://127.0.0.1:8000`** in your browser.

---

## 🔌 API Reference

### 1. Analyze Media URL
- **Endpoint:** `POST /api/v1/playlists/analyze`
- **Request Body:**
  ```json
  {
    "url": "https://www.youtube.com/watch?v=LXb3EKWsInQ",
    "platform_hint": "youtube"
  }
  ```
- **Response:**
  ```json
  {
    "platform": "youtube",
    "type": "single",
    "id": "LXb3EKWsInQ",
    "title": "COSTA RICA IN 4K 60fps HDR (ULTRA HD)",
    "uploader": "Jacob + Katie Schwarz",
    "duration_string": "5:44",
    "thumbnail": "https://i.ytimg.com/vi/...",
    "quality_options": [
      {
        "format_id": "2160p",
        "label": "4K Ultra HD (2160p 60fps)",
        "resolution": "2160p",
        "ext": "mp4",
        "filesize_approx": "1.1 GB",
        "type": "video_audio",
        "note": "Ultra High Definition 4K"
      },
      {
        "format_id": "1440p",
        "label": "2K QHD (1440p 60fps)",
        "resolution": "1440p",
        "ext": "mp4",
        "filesize_approx": "606.7 MB",
        "type": "video_audio",
        "note": "Quad HD 1440p"
      },
      {
        "format_id": "m4a",
        "label": "M4A (AAC 256 kbps)",
        "resolution": "Audio (Apple / iPhone)",
        "ext": "m4a",
        "type": "audio_only",
        "note": "High Fidelity AAC with Tags"
      }
    ]
  }
  ```

### 2. Create Download Job
- **Endpoint:** `POST /api/v1/jobs`
- **Request Body:**
  ```json
  {
    "platform": "youtube",
    "media_type": "single",
    "playlist_id": "LXb3EKWsInQ",
    "playlist_title": "Costa Rica 4K",
    "format": "2160p",
    "tracks": [
      {
        "id": "LXb3EKWsInQ",
        "title": "COSTA RICA IN 4K 60fps HDR",
        "url": "https://www.youtube.com/watch?v=LXb3EKWsInQ",
        "duration": 344,
        "uploader": "Jacob + Katie Schwarz",
        "thumbnail": "https://...",
        "position": 1
      }
    ]
  }
  ```

### 3. Real-Time Progress Stream (SSE)
- **Endpoint:** `GET /api/v1/jobs/{job_id}/stream`
- Streams real-time JSON events with per-track progress percentage and state changes (`ACQUIRING` $\to$ `CONVERTING` $\to$ `VALIDATING` $\to$ `TAGGING` $\to$ `COMPLETED`).

### 4. Download Converted Media / ZIP
- **Single File:** `GET /api/v1/jobs/{job_id}/files/{filename}`
- **Batch ZIP Archive:** `GET /api/v1/jobs/{job_id}/download`

---

## 🧪 Running Automated Tests

Run the complete test suite using `pytest`:
```powershell
cd backend
$env:PYTHONPATH="."
.\.venv\Scripts\pytest.exe tests
```

---

## 📜 License
MIT License. Built for seamless media archiving and high-fidelity offline audio conversion.
