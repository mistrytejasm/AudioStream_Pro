# Playlist Audio Conversion Application — Production Design

## 1. Product Goal

Build a production-grade application where a user:

1. Pastes a playlist URL from a supported source.
2. The application analyzes the playlist and displays its items.
3. The user selects an output format:
   - **MP3** — broadly compatible.
   - **M4A/AAC** — recommended for Apple/iPhone-compatible audio workflows.
4. The user starts processing.
5. The application processes the playlist **one item at a time** (or with configurable worker concurrency), converts each item to the selected format, validates the output, and updates progress in the UI.
6. The user can download the completed files or a ZIP package.

> **Important:** Media acquisition must only be performed where the source permits downloading or where the user has the necessary rights/permission. The design intentionally separates source discovery/acquisition from the conversion pipeline.

---

# 2. Supported Output Formats

## MP3

Use when maximum compatibility is the priority.

Recommended baseline:

- Container: MP3
- Codec: MP3
- Sample rate: 44.1 kHz or source-appropriate rate
- Channels: Stereo when appropriate
- Bitrate: configurable, e.g. 192/256/320 kbps CBR

MP3 is supported by iPhone/iPad and can be imported into Apple Music on supported desktop workflows.

## M4A / AAC

For an Apple/iPhone-oriented workflow, **M4A containing AAC audio** is the recommended choice.

Recommended baseline:

- Container: M4A
- Codec: AAC-LC
- Sample rate: 44.1 kHz
- Channels: Stereo when appropriate
- Bitrate: configurable, e.g. 192–256 kbps

M4A/AAC is widely supported by Apple devices and Apple Music workflows.

### Important terminology

Do not call the format simply "Apple Music format".

Use:

**M4A (AAC)**

The file is an ordinary AAC audio file in an M4A container. Apple Music can work with supported audio formats, but importing/syncing behavior depends on the Apple device, operating system, and Apple Music workflow.

---

# 3. High-Level User Workflow

```text
USER
  |
  | Paste playlist URL
  v
FRONTEND
  |
  | Analyze
  v
FASTAPI
  |
  | Validate URL
  | Create discovery job
  v
QUEUE
  |
  v
DISCOVERY WORKER
  |
  | Obtain permitted playlist metadata
  v
POSTGRESQL
  |
  v
FRONTEND
  |
  | Show playlist items
  | User selects output format
  | MP3 OR M4A (AAC)
  v
CREATE PROCESSING JOB
  |
  v
QUEUE
  |
  v
PROCESSING WORKER
  |
  | One item
  v
AUTHORIZED MEDIA ACQUISITION
  |
  v
TEMPORARY FILE
  |
  v
FFMPEG
  |
  | Convert
  v
OUTPUT AUDIO
  |
  v
FFPROBE / VALIDATION
  |
  +---- invalid ----> RETRY / FAILED
  |
  v
METADATA / TAGGING
  |
  v
OBJECT STORAGE
  |
  v
UPDATE JOB PROGRESS
  |
  v
NEXT ITEM
  |
  v
ALL ITEMS COMPLETE
  |
  v
PACKAGE ZIP (OPTIONAL)
  |
  v
SIGNED DOWNLOAD URL
  |
  v
USER
```

---

# 4. Core Architecture

```text
                         +----------------------+
                         |        USER          |
                         +----------+-----------+
                                    |
                                    v
                         +----------------------+
                         | React / Next.js       |
                         | Frontend              |
                         +----------+-----------+
                                    |
                              HTTPS / WS
                                    |
                                    v
                         +----------------------+
                         | FastAPI               |
                         | API Layer             |
                         +----+------------+-----+
                              |            |
                              |            |
                              v            v
                       +----------+   +----------+
                       |PostgreSQL|   |  Redis   |
                       +----------+   +----+-----+
                                           |
                                           v
                                  +------------------+
                                  | Worker Pool      |
                                  |                  |
                                  | Discovery        |
                                  | Processing       |
                                  | Conversion       |
                                  | Metadata         |
                                  | Packaging        |
                                  +--------+---------+
                                           |
                                           v
                                  +------------------+
                                  | S3 / MinIO       |
                                  | Object Storage   |
                                  +------------------+

                    +--------------------------------+
                    | Observability                   |
                    | Logs / Metrics / Traces         |
                    | Prometheus / Grafana / OTel      |
                    +--------------------------------+
```

---

# 5. Technology Stack

| Layer | Recommended Technology | Notes / Details |
|---|---|---|
| Frontend | React 19 / Next.js 15 (App Router) + Tailwind CSS + shadcn/ui | Clean UI, responsive queue status, SSE/WS streaming |
| API Layer | FastAPI + Pydantic v2 | High-performance async REST API & WebSocket endpoints |
| Database | PostgreSQL 16+ | Durable relational state machine storage |
| ORM / Driver | SQLAlchemy 2.0 (Async) + asyncpg | Pure async queries with transaction management |
| Migrations | Alembic | Schema versioning and automated migrations |
| Queue / Broker | Redis 7+ | Fast job dispatch, pub/sub for real-time progress events |
| Background Workers | ARQ or Celery (async-native with Redis) | Worker isolation, concurrency management, and bounded retries |
| Media Engine | FFmpeg 6.0+ (libmp3lame, aac/libfdk_aac) | Subprocess execution with strict resource/time limits |
| Media Validation | ffprobe + audio decoding pass | Codec/container, duration tolerance & sample check |
| Tagging & Artwork | Mutagen | Embedded ID3v2.4 (MP3) and MP4 iTunes atoms (M4A) |
| Object Storage | MinIO (local dev) / AWS S3 / Cloudflare R2 | Pre-signed download URLs & temporary package cleanup |
| Realtime Progress | Server-Sent Events (SSE) or WebSockets | Live per-track converting/downloading percentage streaming |
| Containerization | Docker & Docker Compose | Uniform local dev environment and production deployment |
| Testing | Pytest + pytest-asyncio + testcontainers | Unit, integration & media pipeline test suites |

---

# 6. Frontend Workflow

## Step 1 — Enter Playlist

UI:

```text
+--------------------------------------------------+
| Playlist Audio Converter                         |
|                                                  |
| Playlist URL                                     |
| +----------------------------------------------+ |
| | https://...                                  | |
| +----------------------------------------------+ |
|                                                  |
|             [ Analyze Playlist ]                 |
+--------------------------------------------------+
```

## Step 2 — Playlist Analysis

Display:

```text
Playlist: My Playlist

Total items: 25

[✓] Track 1
[✓] Track 2
[✓] Track 3
...
[✓] Track 25

Output format:

(o) MP3
( ) M4A (AAC) - Recommended for Apple/iPhone

                 [ Start Processing ]
```

The application should not begin long-running processing during the HTTP request.

---

# 7. Job-Based Processing

When the user clicks Start:

```text
POST /api/v1/jobs
```

The API:

1. Authenticates the user.
2. Validates the request.
3. Validates selected playlist items.
4. Validates output format.
5. Creates a persistent job in PostgreSQL.
6. Creates job-item records.
7. Enqueues processing tasks.
8. Immediately returns a `job_id`.

Example:

```json
{
  "job_id": "job_123",
  "status": "QUEUED",
  "total_items": 25,
  "format": "m4a_aac"
}
```

---

# 8. Processing One Item at a Time

The desired logical workflow is:

```text
Playlist
   |
   v
Track 1
   |
   +--> Acquire
   +--> Convert
   +--> Validate
   +--> Tag
   +--> Store
   |
   v
Track 2
   |
   +--> Acquire
   +--> Convert
   +--> Validate
   +--> Tag
   +--> Store
   |
   v
Track 3
   |
   ...
```

For scalability, the backend should use a queue and worker pool. "One by one" should mean each individual item passes through a controlled state machine; worker concurrency can later be configured.

For a simple initial deployment:

```text
1 worker
1 active item
```

For a larger deployment:

```text
Worker 1 -> Item 1
Worker 2 -> Item 2
Worker 3 -> Item 3
```

The same architecture supports both.

---

# 9. Item State Machine

Each playlist item should have an explicit state.

```text
PENDING
   |
   v
QUEUED
   |
   v
ACQUIRING
   |
   v
ACQUIRED
   |
   v
CONVERTING
   |
   v
CONVERTED
   |
   v
VALIDATING
   |
   v
TAGGING
   |
   v
UPLOADING
   |
   v
COMPLETED
```

Failure:

```text
Any processing state
        |
        v
      FAILED
        |
        v
   Is retryable?
      /     \
    YES      NO
     |        |
     v        v
  RETRY    PERMANENT
```

# 10. Conversion Pipeline & Audio Standards

```text
Input media
     |
     v
Validate input
     |
     v
FFmpeg
     |
     +------------------+
     |                  |
     v                  v
MP3 conversion     M4A/AAC conversion
(libmp3lame)       (aac / libfdk_aac)
     |                  |
     +--------+---------+
              |
              v
           ffprobe
              |
              v
       Validate output
              |
              v
        Metadata tagging (Mutagen)
              |
              v
       Final audio file
```

### Production FFmpeg Parameter Specifications

**1. MP3 (CBR High Quality):**
```bash
ffmpeg -y -i input.ext \
  -vn -sn \
  -c:a libmp3lame -b:a 320k -ar 44100 -ac 2 \
  -map_metadata -1 \
  output.mp3
```

**2. M4A / AAC (Apple/iPhone Optimized):**
```bash
ffmpeg -y -i input.ext \
  -vn -sn \
  -c:a aac -b:a 256k -ar 44100 -ac 2 \
  -movflags +faststart \
  -map_metadata -1 \
  output.m4a
```
*(Note: `-movflags +faststart` relocates the `moov` atom header to the beginning of the file, allowing instant playback/streaming on iOS and Apple Music without needing complete download buffering).*

---

# 11. Preventing Corrupt Audio & Strict Validation

The application must never assume that a zero exit code from FFmpeg proves the final file is valid.

### Validation Checklist:
1. Confirm the FFmpeg process exited with code `0`.
2. Confirm output file exists on disk with `size > 1024` bytes (eliminates zero-byte / truncated headers).
3. Run JSON stream analysis via `ffprobe`:
   ```bash
   ffprobe -v error -show_entries format=duration,format_name,size:stream=codec_name,channels,sample_rate,bit_rate -of json output.ext
   ```
4. **Codec & Format Verification:**
   - For MP3: verify `format_name` contains `mp3` and `codec_name == "mp3"`.
   - For M4A: verify `format_name` contains `mov,mp4,m4a` and `codec_name == "aac"`.
5. **Duration Integrity:** Ensure `abs(output_duration - expected_duration) <= 2.5s` (or within $\le 3\%$).
6. **Sample Integrity Pass (Null Decode Test):**
   Run a brief decoding pass through FFmpeg to detect corrupt frames / truncated bitstreams:
   ```bash
   ffmpeg -v error -i output.ext -f null -
   ```
   If any fatal decoding errors are returned, mark as `CORRUPT_MEDIA` and trigger retry.
7. Only after passing all checks proceed to metadata tagging and MinIO/S3 upload.

Conceptually:

```text
FFmpeg
  |
  v
output.m4a
  |
  v
Does file exist?
  |
  +-- NO --> FAILED
  |
  v
Size > 0?
  |
  +-- NO --> FAILED
  |
  v
ffprobe
  |
  +-- invalid --> FAILED
  |
  v
Audio stream exists?
  |
  +-- NO --> FAILED
  |
  v
Codec correct?
  |
  +-- NO --> FAILED
  |
  v
Duration valid?
  |
  +-- NO --> FAILED
  |
  v
VALID AUDIO
```

This greatly reduces the chance of delivering a corrupted output file.

---

# 12. Format Validation

For MP3:

```text
Expected container: MP3
Expected audio codec: MP3
```

For M4A:

```text
Expected container: MP4/M4A
Expected audio codec: AAC
```

Do not validate only by filename extension.

Bad:

```text
file.m4a
```

The extension alone does not prove that the file is valid M4A/AAC.

Use `ffprobe` to inspect the actual media streams.

---

# 13. Metadata

For each completed track, optionally write:

```text
Title
Artist
Album
Album Artist
Track Number
Disc Number
Year
Genre
Cover Art
```

### Metadata Tag Mapping Specifications

For clean display in Apple Music, iTunes, and standard media players, tags must follow container-specific standards:

| Tag Field | MP3 (ID3v2.4 via `mutagen.id3`) | M4A (iTunes Atoms via `mutagen.mp4`) | Notes |
|---|---|---|---|
| Title | `TIT2` | `\xa9nam` | Sanitized track title |
| Artist | `TPE1` | `\xa9ART` | Primary artist |
| Album Artist | `TPE2` | `aART` | Crucial for grouping tracks under single album in Apple Music |
| Album | `TALB` | `\xa9alb` | Playlist / Album name |
| Track Number | `TRCK` (e.g. `"1/25"`) | `trkn` (tuple `(1, 25)`) | Ensures correct playback sequence |
| Year / Date | `TDRC` (e.g. `"2024"`) | `\xa9day` (e.g. `"2024"`) | Release year |
| Genre | `TCON` | `\xa9gen` | Music genre |
| Cover Art | `APIC` (JPEG/PNG, mime, front cover) | `covr` (`MP4Cover` atom) | Resized square thumbnail (max 1000x1000) |

Pipeline:

```text
Source metadata (Title, Artist, Playlist, Thumbnail)
       |
       v
Normalize & Sanitize (strip illegal chars, limit length)
       |
       v
Fetch & Process Cover Art (JPEG/PNG compression & square crop)
       |
       v
Embed Tags via Mutagen
       |
       v
Validate Tag Readability
```

Metadata should never be trusted blindly from an external source.

---

# 14. File Naming

Use a safe deterministic filename.

Example:

```text
01 - Artist - Track Title.m4a
02 - Artist - Track Title.m4a
```

Sanitize:

```text
/
\
:
*
?
"
<
>
|
```

Also prevent path traversal:

```text
../../file
```

Never directly concatenate an untrusted title into a filesystem path.

---

# 15. Storage

Temporary files:

```text
Worker
  |
  v
/tmp/job_123/item_456/
  |
  +-- input
  |
  +-- output.m4a
```

After successful processing:

```text
output.m4a
   |
   v
S3 / MinIO
   |
   v
Delete temporary file
```

PostgreSQL stores metadata such as:

```text
asset_id
storage_key
format
codec
duration
size_bytes
checksum
```

The actual audio belongs in object storage.

---

# 16. Object Storage Layout

```text
bucket/
|
+-- audio/
|   |
|   +-- job_123/
|       |
|       +-- 001-track.m4a
|       +-- 002-track.m4a
|       +-- 003-track.m4a
|
+-- packages/
    |
    +-- job_123/
        |
        +-- playlist.zip
```

---

# 17. UI Progress

The UI should display both overall and per-track progress.

Example:

```text
Playlist: My Playlist

Format: M4A (AAC)

Overall Progress
[████████████████░░░░] 80%

20 / 25 completed

✓ Track 01       Completed
✓ Track 02       Completed
✓ Track 03       Completed
✓ Track 04       Completed
...
⚙ Track 21       Converting 64%
○ Track 22       Waiting
○ Track 23       Waiting
○ Track 24       Waiting
○ Track 25       Waiting
```

For each active item:

```text
Status: Converting
Progress: 64%
```

---

# 18. Realtime Progress Architecture

```text
                    Worker
                       |
                       | progress event
                       v
                    Redis
                       |
                       v
                   FastAPI
                       |
                 WebSocket/SSE
                       |
                       v
                    Browser
```

Example event:

```json
{
  "job_id": "job_123",
  "item_id": "item_21",
  "status": "CONVERTING",
  "progress": 64
}
```

---

# 19. PostgreSQL Data Model

## users

```text
id
email
created_at
updated_at
```

## playlists

```text
id
source
source_playlist_id
url
title
item_count
status
created_at
updated_at
```

## playlist_items

```text
id
playlist_id
source_item_id
position
title
duration
thumbnail_url
metadata
status
created_at
```

## jobs

```text
id
user_id
playlist_id
status
format
quality
total_items
completed_items
failed_items
created_at
started_at
completed_at
```

## job_items

```text
id
job_id
playlist_item_id
status
attempt_count
error_code
error_message
started_at
completed_at
```

## media_assets

```text
id
job_item_id
storage_key
format
codec
size_bytes
duration
checksum
status
created_at
```

## packages

```text
id
job_id
storage_key
size_bytes
checksum
expires_at
status
```

---

# 20. API Design

Use API versioning:

```text
/api/v1/
```

### Analyze

```http
POST /api/v1/playlists/analyze
```

### Playlist

```http
GET /api/v1/playlists/{playlist_id}
GET /api/v1/playlists/{playlist_id}/items
```

### Jobs

```http
POST /api/v1/jobs
GET /api/v1/jobs/{job_id}
POST /api/v1/jobs/{job_id}/cancel
POST /api/v1/jobs/{job_id}/retry
```

### Job items

```http
GET /api/v1/jobs/{job_id}/items
GET /api/v1/jobs/{job_id}/items/{item_id}
```

### Download

```http
GET /api/v1/jobs/{job_id}/download
```

For large files, FastAPI should return a short-lived signed object-storage URL rather than proxying the entire file through the API.

---

# 21. Idempotency

The system must tolerate duplicate requests and worker retries.

Conceptually create a deterministic key from:

```text
source
source_item_id
output_format
quality
```

Then:

```text
Does validated asset already exist?
        |
     YES|NO
        | \
        |  \
        v   v
      SKIP  PROCESS
```

This prevents unnecessary duplicate conversion.

---

# 22. Retry Strategy

Use bounded retries.

Example:

```text
Attempt 1
   |
   v
2 seconds
   |
Attempt 2
   |
   v
5 seconds
   |
Attempt 3
   |
   v
15 seconds
   |
Attempt 4
   |
   v
Permanent failure
```

Use exponential backoff with jitter.

Do not retry permanent errors such as an invalid input indefinitely.

---

# 23. Error Classification

Use structured errors:

```text
SOURCE_UNAVAILABLE
SOURCE_RATE_LIMITED
AUTHORIZATION_REQUIRED
MEDIA_NOT_PERMITTED
NETWORK_ERROR
TIMEOUT
INVALID_MEDIA
FFMPEG_ERROR
VALIDATION_ERROR
STORAGE_ERROR
METADATA_ERROR
PACKAGE_ERROR
UNKNOWN_ERROR
```

Each error should have:

```text
retryable = true/false
```

---

# 24. Security

Because users provide URLs and external media is processed, security is critical.

Implement:

- HTTPS
- Authentication if multi-user
- Authorization
- Rate limiting
- Request limits
- Playlist-size limits
- URL validation
- SSRF protection
- Filename sanitization
- Path traversal protection
- Safe subprocess execution
- FFmpeg timeouts
- CPU limits
- Memory limits
- Temporary storage limits
- Signed download URLs
- Secret management
- Structured audit logs

Never execute shell commands by interpolating untrusted user input.

---

# 25. SSRF Protection

Because the application accepts URLs:

```text
User URL
   |
   v
Parse URL
   |
   v
Validate scheme
   |
   v
Validate allowed source
   |
   v
Resolve DNS
   |
   v
Reject private/internal IPs
   |
   v
Fetch
```

Do not build a generic unrestricted server-side URL fetcher.

---

# 26. Worker Isolation

FFmpeg processing should run outside the FastAPI request process.

```text
FastAPI
   |
   v
Queue
   |
   v
Media Worker
   |
   v
FFmpeg
```

Media workers should have:

- restricted permissions
- ephemeral filesystem
- CPU limits
- memory limits
- execution timeouts
- output-size limits

---

# 27. Failure Recovery

The application must survive:

```text
FastAPI crash
Worker crash
Redis restart
PostgreSQL restart
MinIO/S3 outage
Network failure
FFmpeg failure
Duplicate task
Browser refresh
User closing browser
```

The database is the durable source of job state.

Redis is used for queues/cache/events, not as the only source of truth.

Example worker crash:

```text
Worker 1
   |
   | Processing Track 7
   X
  CRASH
   |
   v
Queue retry
   |
   v
Worker 2
   |
   v
Track 7 resumes
```

---

# 28. Local End-to-End Environment (Docker Compose)

The entire architecture runs locally with unified Docker Compose orchestration.

```text
+-------------------------------------------------------+
|                    LOCAL MACHINE                      |
|                                                       |
|  Browser                                               |
|     |                                                  |
|     v                                                  |
|  Frontend (Port 3000)                                  |
|     |                                                  |
|     v                                                  |
|  FastAPI (Port 8000)                                   |
|     |                                                   |
|     +--------> PostgreSQL (Port 5432)                  |
|     |                                                   |
|     +--------> Redis (Port 6379)                       |
|               |                                        |
|               v                                        |
|            Workers (ARQ / Celery)                      |
|               |                                        |
|               v                                        |
|             FFmpeg + ffprobe (inside worker container) |
|               |                                        |
|               v                                        |
|             MinIO (Port 9000 / Console 9001)           |
|                                                       |
+-------------------------------------------------------+
```

### Standard Project Layout

```text
d:\AI_Projects\youtube_playlist_download\
├── docker-compose.yml
├── .env.example
├── backend/
│   ├── Dockerfile
│   ├── pyproject.toml
│   ├── alembic/
│   └── app/
│       ├── main.py             # FastAPI App & SSE/WS routes
│       ├── config.py           # Pydantic Settings
│       ├── db/                 # SQLAlchemy 2.0 async models & sessions
│       ├── services/           # Media conversion, validation, tagging, S3
│       ├── workers/            # Task definitions & retry handling
│       └── schemas/            # Pydantic request/response schemas
└── frontend/
    ├── Dockerfile
    ├── package.json
    ├── src/
    │   ├── app/                # Next.js App Router
    │   ├── components/         # Playlist table, progress bars, audio format selector
    │   └── hooks/              # useJobProgress (SSE/WS stream)
```

---

# 29. Local Failure Testing

Intentionally stop services.

## Worker crash

```bash
docker stop worker
```

Verify the job eventually retries.

## Redis failure

```bash
docker stop redis
```

Verify graceful degradation and recovery.

## PostgreSQL failure

```bash
docker stop postgres
```

Verify API errors are controlled and jobs remain recoverable.

## Object storage failure

```bash
docker stop minio
```

Verify upload retries.

These tests are essential for a fail-resistant application.

---

# 30. Testing Strategy

## Unit Tests

Test:

```text
URL validation
format validation
filename sanitization
metadata normalization
state transitions
retry calculation
idempotency
```

## Integration Tests

Test:

```text
FastAPI
+
PostgreSQL
+
Redis
+
Worker
+
MinIO
```

## Media Tests

Use known test media:

```text
valid audio
valid video
corrupt media
zero-byte file
unsupported codec
missing audio stream
incorrect duration
```

## End-to-End Test

```text
Playlist/Test Source
       |
       v
Analyze
       |
       v
Select format
       |
       v
Create job
       |
       v
Process all items
       |
       v
Validate every output
       |
       v
Store
       |
       v
Package
       |
       v
Download
       |
       v
Verify files play correctly
```

---

# 31. Production Architecture

```text
                         INTERNET
                            |
                            v
                    Load Balancer / Ingress
                            |
                            v
                  +-----------------------+
                  | FastAPI Pods          |
                  | 2..N replicas         |
                  +----------+------------+
                             |
             +---------------+---------------+
             |                               |
             v                               v
       PostgreSQL                         Redis
       Managed DB                         Queue
             |                               |
             |                    +----------+----------+
             |                    |                     |
             |                    v                     v
             |             Discovery Workers     Media Workers
             |                                      |
             |                                      v
             |                                    FFmpeg
             |                                      |
             +------------------+-------------------+
                                |
                                v
                              S3
                                |
                                v
                         Signed Download URL
                                |
                                v
                              USER
```

---

# 32. Development Roadmap

## Phase 1 — Basic Pipeline

Build:

```text
FastAPI
PostgreSQL
Redis
Worker
FFmpeg
```

Process local test media first.

```text
test.mp4
   |
   v
Worker
   |
   v
FFmpeg
   |
   v
output.m4a
```

Do not integrate an external media source yet.

## Phase 2 — Validation

Add:

```text
ffprobe
checksums
duration validation
codec validation
corruption detection
```

## Phase 3 — Object Storage

Add:

```text
MinIO
S3-compatible storage
signed URLs
```

## Phase 4 — Playlist Workflow

Add:

```text
playlist analysis
playlist items
selection
job creation
```

## Phase 5 — UI

Add:

```text
playlist URL
format selection
start button
progress
errors
download
```

## Phase 6 — Reliability

Add:

```text
retries
idempotency
state machine
timeouts
failure recovery
```

## Phase 7 — Observability

Add:

```text
structured logging
metrics
Prometheus
Grafana
OpenTelemetry
```

## Phase 8 — Security

Add:

```text
authentication
authorization
rate limiting
SSRF protection
subprocess isolation
resource limits
```

## Phase 9 — Load Testing

Test:

```text
1 job
10 jobs
50 jobs
100 jobs
```

and measure:

```text
CPU
RAM
queue depth
processing time
database load
storage
worker throughput
```

## Phase 10 — Production Deployment

Move:

```text
Docker Compose
```

to:

```text
Kubernetes
+
Managed PostgreSQL
+
Managed Redis
+
S3
```

---

# 33. Final Recommended User Experience

The final UI should be as simple as:

```text
+------------------------------------------------------+
|              Playlist Audio Converter                |
+------------------------------------------------------+
|                                                      |
| Playlist URL                                         |
|                                                      |
| [ https://...                                      ] |
|                                                      |
|                 [ Analyze Playlist ]                 |
|                                                      |
+------------------------------------------------------+

After analysis:

+------------------------------------------------------+
| My Playlist                                          |
| 25 tracks                                            |
|                                                      |
| [✓] Track 01                                         |
| [✓] Track 02                                         |
| [✓] Track 03                                         |
| ...                                                  |
|                                                      |
| Output Format                                        |
|                                                      |
| ( ) MP3                                              |
| (•) M4A (AAC) — Recommended for Apple/iPhone        |
|                                                      |
|                  [ Start Processing ]                |
+------------------------------------------------------+

During processing:

+------------------------------------------------------+
| Processing Playlist                                  |
|                                                      |
| Overall                                              |
| [████████████████░░░░] 80%                          |
|                                                      |
| 20 / 25 completed                                    |
|                                                      |
| ✓ Track 01      Completed                            |
| ✓ Track 02      Completed                            |
| ✓ Track 03      Completed                            |
| ⚙ Track 21      Converting — 64%                    |
| ○ Track 22      Waiting                              |
| ○ Track 23      Waiting                              |
|                                                      |
+------------------------------------------------------+

Completion:

+------------------------------------------------------+
| ✓ Processing Complete                                |
|                                                      |
| 25 / 25 files successfully processed                 |
|                                                      |
| Format: M4A (AAC)                                   |
|                                                      |
|             [ Download ZIP ]                         |
+------------------------------------------------------+
```

---

# 34. Key Design Principles

1. **API never performs long-running media processing.**
2. **Workers perform processing.**
3. **PostgreSQL is the durable source of truth.**
4. **Redis is for queues/cache/events.**
5. **FFmpeg is isolated from FastAPI.**
6. **Every item has an explicit state.**
7. **Every failure is classified.**
8. **Retries are bounded and idempotent.**
9. **Every converted file is validated before completion.**
10. **Large files live in object storage.**
11. **The browser receives progress through WebSocket/SSE.**
12. **Downloads use signed object-storage URLs.**
13. **Temporary files are deleted after successful processing.**
14. **External URLs are validated and protected against SSRF.**
15. **The application must be testable entirely on a local Docker Compose environment.**

---

# 35. Final Answer to the Format/Corruption Question

Yes, the application can reliably produce both:

**MP3**
- Broadly compatible.
- Suitable for iPhone/iPad playback and common music-library workflows.

**M4A (AAC)**
- The recommended Apple/iPhone-oriented choice.
- Widely supported by Apple devices and Apple Music workflows.

The important part is not merely choosing the extension. The application should explicitly encode the desired codec/container and then validate the resulting file with `ffprobe`.

A robust pipeline is:

```text
Input
  |
  v
FFmpeg
  |
  +---- MP3 ---> MP3 container + MP3 audio
  |
  +---- M4A ---> M4A/MP4 container + AAC audio
                    |
                    v
                 ffprobe
                    |
                    v
              Validate stream
                    |
                    v
              Validate duration
                    |
                    v
              Validate file size
                    |
                    v
            Mark COMPLETED
```

No software can honestly guarantee that every possible source file will convert successfully without error. However, with proper FFmpeg error handling, timeouts, retries, output validation, duration checks, and integrity checks, the application can be designed to **avoid presenting a corrupt or invalid file as successfully completed**.

For Apple/iPhone use, label the option **"M4A (AAC) — Recommended for Apple/iPhone"**, rather than claiming that it is a special proprietary "Apple Music format."
