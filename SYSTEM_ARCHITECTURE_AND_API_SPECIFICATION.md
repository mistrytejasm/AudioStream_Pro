# AudioStream Pro — Complete System Architecture & API Specification

An exhaustive, end-to-end technical guide for **AudioStream Pro**, a high-performance multi-platform media downloader, FFmpeg audio/video conversion engine, and real-time streaming system.

---

## 📑 Table of Contents
1. [Executive Summary & High-Level Architecture](#1-executive-summary--high-level-architecture)
2. [End-to-End System Workflow (Step-by-Step)](#2-end-to-end-system-workflow-step-by-step)
3. [Component-Level Architecture](#3-component-level-architecture)
4. [FFmpeg Transcoding & Media Muxing Pipelines](#4-ffmpeg-transcoding--media-muxing-pipelines)
5. [Strict 4-Point Media Validation Pipeline](#5-strict-4-point-media-validation-pipeline)
6. [Fault Tolerance & Smart Recovery Engine](#6-fault-tolerance--smart-recovery-engine)
7. [Complete REST & SSE API Reference](#7-complete-rest--sse-api-reference)
8. [Data Models & State Machine Specifications](#8-data-models--state-machine-specifications)
9. [Frontend Architecture & Real-Time SSE Binding](#9-frontend-architecture--real-time-sse-binding)
10. [Local Development & Deployment Guide](#10-local-development--deployment-guide)

---

## 1. Executive Summary & High-Level Architecture

AudioStream Pro is designed as a **zero-corruption, high-fidelity media extraction and conversion platform**. It bridges external content providers (**YouTube, Instagram, X/Twitter, Facebook**) with an internal processing engine powered by **FastAPI**, **yt-dlp**, and **FFmpeg**.

### High-Level Architecture Diagram
```
+---------------------------------------------------------------------------------------+
|                                    USER BROWSER                                       |
|  - Platform Selector (YouTube, IG, X, FB)  - Quality Matrix (4K, 2K, 1080p, M4A, MP3) |
|  - Real-Time SSE Progress Engine           - Single & Batch ZIP Download Triggers     |
+------------------------------------------+--------------------------------------------+
                                           | HTTP Requests & SSE Connection
                                           v
+---------------------------------------------------------------------------------------+
|                                  FASTAPI APPLICATION                                  |
|                                                                                       |
|  [REST API Routes] (/api/v1/playlists/analyze, /jobs, /tracks/retry, /files, etc.)   |
|                                           |                                           |
|  [Multi-Platform Analyzer] (Domain detection, SSRF protection, resolution scanner)     |
|                                           |                                           |
|  [Job State Manager] (Asynchronous State Machine, Threadpool Execution, SSE Broadcast)|
+-------------------+-----------------------+--------------------+----------------------+
                    |                       |                    |
                    v                       v                    v
          +-------------------+   +--------------------+   +--------------------+
          |      yt-dlp       |   |   FFmpeg Engine    |   |  Mutagen Tagger    |
          | (Raw Stream Extr) |   | (Video/Audio Mux)  |   | (ID3v2.4 & iTunes) |
          +-------------------+   +--------------------+   +--------------------+
                    |                       |                    |
                    +-----------------------+--------------------+
                                            |
                                            v
                                 +--------------------+
                                 | 4-Point Validator  |
                                 | (Probe, Size,      |
                                 |  Tolerance, Null)  |
                                 +--------------------+
                                            |
                                            v
                                 +--------------------+
                                 | ZIP Packager       |
                                 | & Storage Delivery |
                                 +--------------------+
```

---

## 2. End-to-End System Workflow (Step-by-Step)

The lifecycle of every download follows an unalterable sequence of 7 deterministic phases:

```
[1. URL Input] ──> [2. Multi-Platform Analysis] ──> [3. Quality Matrix Presentation]
                                                                  │
                                                        (User selects format)
                                                                  ▼
[7. File/ZIP Delivery] ◄── [6. Metadata Tagging] ◄── [5. Strict Validation] ◄── [4. Acquiring & Transcoding]
```

### Step 1: Input & SSRF Verification
- User inputs a URL (or selects a platform tab).
- Backend executes `is_safe_url()` to verify that the IP resolved from the domain is neither private (e.g. `127.0.0.1`, `192.168.x.x`), loopback, nor reserved, mitigating **Server-Side Request Forgery (SSRF)** attacks.

### Step 2: Multi-Platform Analysis & Stream Harvesting
- `MultiPlatformAnalyzerService` uses `detect_platform()` to detect the platform (`youtube`, `instagram`, `twitter`, `facebook`, `generic`).
- `yt-dlp` extracts information non-destructively (`skip_download=True`).
- Identifies whether the content is a **Single Media Item** or a **Playlist**.

### Step 3: Dynamic Resolution & Format Mapping
- The backend iterates over all available raw video streams.
- It groups unique heights into a descending ladder:
  - **4K Ultra HD** (`2160p`)
  - **2K Quad HD** (`1440p`)
  - **1080p Full HD** (`1080p`)
  - **720p HD**, **480p SD**, **360p**, **240p**, **144p**
  - **Audio Formats**: Apple/iPhone M4A (256k AAC) & Universal MP3 (320k CBR).
- An estimated file size is calculated and returned to the frontend.

### Step 4: Job Creation & Asynchronous Worker Dispatch
- User picks a format (e.g. `2160p` or `m4a`) and initiates the job.
- `JobManager` generates a unique `job_id` (e.g. `job_a1b2c3d4e5`), initializes state models, and spawns an asynchronous worker task in the background.

### Step 5: Acquiring Source Stream
- The worker executes `yt-dlp` in a threadpool to acquire the stream into a dedicated temporary folder (`storage/temp/{job_id}`).
- For video formats (e.g. 4K/2K), `yt-dlp` acquires the separate best video stream and best audio stream.

### Step 6: FFmpeg Encoding & Muxing
- **For Video (`MP4`):** FFmpeg muxes separate video and audio streams into an H.264/AAC MP4 container with `-movflags +faststart` to allow instant streaming playback.
- **For Audio (`M4A` / `MP3`):** FFmpeg converts the audio stream into exact CBR standards (256 kbps AAC or 320 kbps MP3).

### Step 7: Strict 4-Point Validation & Tagging
- Converted media is subjected to size, `ffprobe` stream structure, duration tolerance, and null-decode integrity verification.
- If audio, `mutagen` writes ID3v2.4 frames or iTunes MP4 atoms, embedding album art.
- File is moved to `storage/output/{job_id}` and marked `COMPLETED` on the SSE stream.

---

## 3. Component-Level Architecture

### Directory Layout & Roles
```
backend/app/
├── config.py              # Central Pydantic Settings (paths, limits, bitrates)
├── main.py                # FastAPI lifecycle, CORS, static file routing
├── models/
│   └── job.py             # Data contracts, schemas, and enumerations
├── routes/
│   └── api.py             # HTTP REST controllers and SSE event endpoints
└── services/
    ├── ffmpeg_finder.py   # Binary discovery (System PATH & static-ffmpeg)
    ├── subprocess_runner.py # Threadpool-based Windows-safe async process executor
    ├── validator.py       # Multi-point media integrity verifier
    ├── converter.py       # Audio encoding & Video muxing pipelines
    ├── tagger.py          # ID3v2.4 and MP4 atom metadata injector
    ├── packager.py        # ZIP archiver
    ├── playlist.py        # Multi-platform content analysis service
    └── job_manager.py     # Central state machine, dispatcher, and SSE broker
```

---

## 4. FFmpeg Transcoding & Media Muxing Pipelines

All FFmpeg commands are executed via `subprocess_runner.py` with standard I/O streaming, preventing GUI popups or Windows thread deadlocks.

### 1. MP3 Universal High-Fidelity Pipeline (320 kbps CBR)
```bash
ffmpeg -y -v error -i <input_raw> \
  -vn \
  -c:a libmp3lame \
  -b:a 320k \
  -ar 44100 \
  -ac 2 \
  <output_file>.mp3
```
- `-vn`: Strips any video or dummy picture streams to avoid codec mismatch.
- `-c:a libmp3lame -b:a 320k`: Forces Constant Bitrate (CBR) 320 kbps for maximum fidelity.
- `-ar 44100 -ac 2`: Enforces standard CD-quality sample rate and stereo channel topology.

### 2. M4A Apple / iPhone Optimized Pipeline (256 kbps AAC)
```bash
ffmpeg -y -v error -i <input_raw> \
  -vn \
  -c:a aac \
  -b:a 256k \
  -ar 44100 \
  -ac 2 \
  -movflags +faststart \
  <output_file>.m4a
```
- `-movflags +faststart`: Relocates the `moov` index atom to the beginning of the file, allowing instant streaming and zero-delay playback on Apple Music and iOS devices.

### 3. Video Muxing Pipeline (4K, 2K, 1080p MP4)
```bash
ffmpeg -y -v error -i <input_raw_or_separate_streams> \
  -c:v copy \
  -c:a aac \
  -b:a 192k \
  -movflags +faststart \
  <output_file>.mp4
```
- `-c:v copy`: Direct stream copy of high-resolution video streams without re-encoding, preserving 100% of original visual quality at maximum speed.
- `-c:a aac -b:a 192k`: Re-encodes accompanying audio stream into standard AAC.

---

## 5. Strict 4-Point Media Validation Pipeline

Implemented in [`app/services/validator.py`](file:///d:/AI_Projects/youtube_playlist_download/backend/app/services/validator.py). Every output file must pass 4 sequential gates:

```
[Gate 1: File Size Check]  ──> > 1024 Bytes
           │
[Gate 2: ffprobe Analysis] ──> Valid stream count, matching codec, valid sample rate
           │
[Gate 3: Duration Check]   ──> Converted duration within 3% of source duration
           │
[Gate 4: Null-Decode Pass] ──> ffmpeg -v error -i <file> -f null - (Exit Code 0)
```

1. **Size Integrity Check:** File size must exceed 1024 bytes (guards against truncated files or 0-byte failures).
2. **`ffprobe` JSON Stream Inspection:**
   ```bash
   ffprobe -v quiet -print_format json -show_format -show_streams <converted_file>
   ```
   Ensures audio stream exists with correct codec (`mp3` or `aac`) and audio channels $\ge 1$.
3. **Duration Tolerance Verification:**
   $$\left| \text{Duration}_{\text{converted}} - \text{Duration}_{\text{source}} \right| \le \max(2.0\text{s}, 0.03 \times \text{Duration}_{\text{source}})$$
4. **Null-Decode Integrity Pass:**
   ```bash
   ffmpeg -v error -i <converted_file> -f null -
   ```
   Renders and decodes every frame to a null sink. If corrupted frames or broken bitstream headers are found, FFmpeg throws an exit code $\neq 0$, automatically rejecting the file.

---

## 6. Fault Tolerance & Smart Recovery Engine

When processing large playlists or third-party streams, failures can occasionally happen (bot checks, deleted videos, network drops). AudioStream Pro provides three layers of automated recovery:

```
                                  TRACK FAILS
                                       │
                ┌──────────────────────┼──────────────────────┐
                ▼                      ▼                      ▼
        [1. Manual Retry]      [2. Auto-Resolve]      [3. Custom URL Sub]
        (Instant re-queue)     (AI YouTube Search     (User supplies working
                                for mirror track)      alternative URL)
                │                      │                      │
                └──────────────────────┼──────────────────────┘
                                       ▼
                       [Track Successfully Converted]
                                       │
                                       ▼
                        [Auto-Repackage Playlist ZIP]
```

1. **Manual Retry (`POST /jobs/{job_id}/tracks/{track_id}/retry`):** Re-runs acquisition and transcoding for the specific track without affecting completed files.
2. **Smart Auto-Resolve (`POST /jobs/{job_id}/tracks/{track_id}/auto-resolve`):** Searches YouTube for working alternative mirrors (`ytsearch1:{artist} - {title} audio`), verifies match, and automatically completes the conversion.
3. **Custom URL Substitution (`POST /jobs/{job_id}/tracks/{track_id}/substitute`):** Allows users to paste an alternative URL for unavailable videos.
4. **Automatic ZIP Repackaging:** Once any failed track is recovered, `JobManager.repackage_zip()` automatically rebuilds the ZIP archive so the download button delivers all items.

---

## 7. Complete REST & SSE API Reference

Base URL: `http://localhost:8000/api/v1`

---

### 1. Analyze Media URL
Extracts metadata, detected platform, available video resolutions (8K/4K/2K/1080p), and audio options.

- **Method:** `POST`
- **Path:** `/playlists/analyze`
- **Request Body:**
  ```json
  {
    "url": "https://www.youtube.com/watch?v=LXb3EKWsInQ",
    "platform_hint": "youtube"
  }
  ```
- **Response `200 OK` (Single Video Example):**
  ```json
  {
    "platform": "youtube",
    "type": "single",
    "id": "LXb3EKWsInQ",
    "title": "COSTA RICA IN 4K 60fps HDR (ULTRA HD)",
    "uploader": "Jacob + Katie Schwarz",
    "duration": 344.0,
    "duration_string": "5:44",
    "thumbnail": "https://i.ytimg.com/vi/LXb3EKWsInQ/maxresdefault.jpg",
    "url": "https://www.youtube.com/watch?v=LXb3EKWsInQ",
    "item_count": 1,
    "items": [
      {
        "id": "LXb3EKWsInQ",
        "title": "COSTA RICA IN 4K 60fps HDR (ULTRA HD)",
        "duration": 344.0,
        "duration_string": "5:44",
        "uploader": "Jacob + Katie Schwarz",
        "thumbnail": "https://i.ytimg.com/vi/LXb3EKWsInQ/maxresdefault.jpg",
        "url": "https://www.youtube.com/watch?v=LXb3EKWsInQ"
      }
    ],
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
        "format_id": "1080p",
        "label": "1080p Full HD 60fps",
        "resolution": "1080p",
        "ext": "mp4",
        "filesize_approx": "250.3 MB",
        "type": "video_audio",
        "note": "FHD High Quality"
      },
      {
        "format_id": "m4a",
        "label": "M4A (AAC 256 kbps)",
        "resolution": "Audio (Apple / iPhone)",
        "ext": "m4a",
        "filesize_approx": null,
        "type": "audio_only",
        "note": "High Fidelity AAC with Tags"
      },
      {
        "format_id": "mp3",
        "label": "MP3 (320 kbps CBR)",
        "resolution": "Audio (Universal)",
        "ext": "mp3",
        "filesize_approx": null,
        "type": "audio_only",
        "note": "Maximum Quality MP3 with ID3v2.4"
      }
    ]
  }
  ```

---

### 2. Create Download & Conversion Job
Creates a background conversion job for a single video or batch of playlist tracks.

- **Method:** `POST`
- **Path:** `/jobs`
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
        "title": "COSTA RICA IN 4K 60fps HDR (ULTRA HD)",
        "url": "https://www.youtube.com/watch?v=LXb3EKWsInQ",
        "duration": 344.0,
        "uploader": "Jacob + Katie Schwarz",
        "thumbnail": "https://i.ytimg.com/vi/LXb3EKWsInQ/maxresdefault.jpg",
        "position": 1
      }
    ]
  }
  ```
- **Response `200 OK`:**
  ```json
  {
    "job_id": "job_9b3f07a2d1",
    "platform": "youtube",
    "media_type": "single",
    "playlist_title": "Costa Rica 4K",
    "format": "2160p",
    "status": "QUEUED",
    "total_tracks": 1,
    "completed_tracks": 0,
    "failed_tracks": 0,
    "tracks": {
      "LXb3EKWsInQ": {
        "id": "LXb3EKWsInQ",
        "title": "COSTA RICA IN 4K 60fps HDR (ULTRA HD)",
        "position": 1,
        "status": "PENDING",
        "progress": 0,
        "error": null,
        "download_url": null
      }
    },
    "zip_download_url": null,
    "error": null
  }
  ```

---

### 3. Real-Time Progress Stream (Server-Sent Events)
Connects an open event stream to receive live progress updates whenever track status or percentage updates.

- **Method:** `GET`
- **Path:** `/jobs/{job_id}/stream`
- **Response Header:** `Content-Type: text/event-stream`
- **Stream Event Payload Example:**
  ```
  data: {"job_id":"job_9b3f07a2d1","status":"PROCESSING","completed_tracks":0,"tracks":{"LXb3EKWsInQ":{"status":"CONVERTING","progress":50}}}
  ```

---

### 4. Retry Failed Track
- **Method:** `POST`
- **Path:** `/jobs/{job_id}/tracks/{track_id}/retry`
- **Response `200 OK`:** `{"status": "retry_scheduled", "track_id": "LXb3EKWsInQ"}`

---

### 5. Auto-Resolve Track Alternative
- **Method:** `POST`
- **Path:** `/jobs/{job_id}/tracks/{track_id}/auto-resolve`
- **Response `200 OK`:** `{"status": "auto_resolve_scheduled", "track_id": "LXb3EKWsInQ"}`

---

### 6. Substitute Track URL
- **Method:** `POST`
- **Path:** `/jobs/{job_id}/tracks/{track_id}/substitute`
- **Request Body:** `{"url": "https://www.youtube.com/watch?v=alternative_id"}`
- **Response `200 OK`:** `{"status": "substitute_scheduled", "track_id": "LXb3EKWsInQ"}`

---

### 7. Download Direct Single File
- **Method:** `GET`
- **Path:** `/jobs/{job_id}/files/{filename}`
- **Response:** Binary Stream (`video/mp4`, `audio/mp4`, or `audio/mpeg`) with `Content-Disposition: attachment`.

---

### 8. Download Playlist ZIP Archive
- **Method:** `GET`
- **Path:** `/jobs/{job_id}/download`
- **Response:** Binary ZIP stream (`application/zip`).

---

## 8. Data Models & State Machine Specifications

### Track Processing State Machine
```
[PENDING] (0%)
    │
    ▼
[ACQUIRING] (15%) ──> Raw stream downloaded from provider
    │
    ▼
[CONVERTING] (50%) ──> FFmpeg encoding audio / muxing 4K/2K/HD MP4
    │
    ▼
[VALIDATING] (80%) ──> ffprobe stream verification & null-decode check
    │
    ▼
[TAGGING] (90%) ────> Mutagen embeds ID3v2.4 or MP4 atoms
    │
    ▼
[COMPLETED] (100%) ──> Download URL generated & ZIP repackaged
    │
    └─► If error occurs at any stage ──► [FAILED] (Error recorded & recovery options exposed)
```

---

## 9. Frontend Architecture & Real-Time SSE Binding

The frontend ([`app/static/index.html`](file:///d:/AI_Projects/youtube_playlist_download/backend/app/static/index.html)) is built with **vanilla JavaScript** and **Tailwind CSS**.

### Key Frontend Mechanisms:
1. **Interactive Platform Hub:** Switches placeholders and hints for `YouTube`, `Instagram`, `X (Twitter)`, and `Facebook`.
2. **Quality Matrix Rendering:** Renders responsive tables with visual badges for `4K UHD`, `2K QHD`, and `FHD`.
3. **Zero-Polling SSE Listener:**
   ```javascript
   const evtSource = new EventSource(`/api/v1/jobs/${jobId}/stream`);
   evtSource.onmessage = function(event) {
       const job = JSON.parse(event.data);
       updateProgressUI(job);
   };
   ```
4. **Adaptive Error Recovery UI:** Injects `Retry`, `Auto-Find Working Audio`, and `Paste Custom URL` controls directly onto failed items without page refreshes.

---

## 10. Local Development & Deployment Guide

### System Requirements
- OS: Windows, macOS, or Linux
- Python: `3.10` or higher (Python `3.12` recommended)
- FFmpeg installed and accessible in system `PATH` (or automated fallback via `static-ffmpeg`)

### Step-by-Step Installation
```powershell
# 1. Clone repository
git clone https://github.com/mistrytejasm/AudioStream_Pro.git
cd AudioStream_Pro

# 2. Navigate to backend directory
cd backend

# 3. Create and activate virtual environment
python -m venv .venv
.\.venv\Scripts\Activate.ps1   # On Windows
# source .venv/bin/activate    # On Linux/macOS

# 4. Install dependencies
pip install -r ../requirements.txt

# 5. Run test suite to verify FFmpeg & pipeline
$env:PYTHONPATH="."
.\.venv\Scripts\pytest.exe tests

# 6. Start the server
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
```
Open **`http://127.0.0.1:8000`** in your browser.
