# Playlist Audio Converter — Quick Start Guide

A production-grade playlist audio conversion application with real-time SSE progress streaming, zero-corruption multi-step FFmpeg/ffprobe validation, ID3/MP4 metadata tagging, and zip archive generation.

---

## How to Run the Application

### 1. Launch the Server
From the project root:
`powershell
cd backend
.\.venv\Scripts\python.exe -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload
`

### 2. Open the Web Application
Open your browser and navigate to:
`
http://127.0.0.1:8000
`

---

## Features & Architecture Highlights

1. **Simple, Intuitive 3-Step UI:**
   - **Step 1:** Paste any YouTube playlist or track URL and click **Analyze**.
   - **Step 2:** Review track titles, artists, durations, and pick format:
     - **M4A (AAC)** — 256 kbps AAC with +faststart atom, optimized for iPhone & Apple Music.
     - **MP3** — 320 kbps CBR with ID3v2.4 tags for universal playback.
   - **Step 3:** Watch live per-track state machines (Acquiring -> Converting -> Validating -> Tagging -> Done) and download individual tracks or the complete ZIP package.

2. **Strict Media Validation Pipeline:**
   - Pre-validation and post-validation with fprobe JSON stream inspection.
   - Size check (>1024 bytes) to guard against empty or truncated headers.
   - Duration verification against source media.
   - FFmpeg null decode pass to identify frame corruption before marking completed.

3. **Metadata & High-Res Cover Art:**
   - Embedded ID3v2.4 frames for MP3.
   - Embedded iTunes MP4 atoms for M4A.
   - Square-cropped cover art fetched directly from the source media.
