# AI Viral Clipper

A self-hosted MVP that accepts a YouTube URL (where access is permitted) or an uploaded video, creates vertical 9:16 MP4 clips, extracts a thumbnail, and suggests hashtags.

## Requirements
- Python 3.10+
- FFmpeg + FFprobe installed and available on PATH
- Internet access for yt-dlp YouTube URL support

## Run locally
### Windows
1. Install FFmpeg from https://ffmpeg.org/download.html and add its `bin` folder to PATH.
2. Open a terminal in this project folder.
3. Run:
   ```powershell
   py -m venv .venv
   .venv\Scripts\activate
   pip install -r requirements.txt
   uvicorn app:app --reload
   ```
4. Open http://127.0.0.1:8000

### macOS
```bash
brew install ffmpeg
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload
```

### Ubuntu / Debian
```bash
sudo apt update && sudo apt install -y ffmpeg python3-venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
uvicorn app:app --reload
```

## Docker
Install Docker Desktop / Docker Engine, then:
```bash
docker compose up --build
```
Open http://localhost:8000

## Optional auto subtitles
The app supports optional Whisper speech-to-text subtitles. Install:
```bash
pip install faster-whisper
```
Set environment variable `ENABLE_WHISPER=1` before starting the server. The first run downloads the selected model. CPU transcription can be slow. Captions are delivered as an SRT file; they are not burned into the clip in this MVP.

## Current MVP behaviour / limitations
- Clip selection uses evenly spaced segments, not AI semantic highlight detection.
- Vertical framing uses a centered crop. A future version can add face tracking / speaker-aware reframing.
- Hashtags are generated from the video title, not predicted virality.
- Thumbnail is a frame extracted from the source, not a generated AI design.
- YouTube downloading depends on yt-dlp, video availability, and YouTube changes. Only process videos you own or have permission to download/edit. Do not bypass DRM, access controls, or platform restrictions.
- This is a development starter, not production-hardened. Before public deployment add authentication, upload size limits, job queue, rate limiting, storage cleanup, HTTPS, and malware scanning.

## API
`POST /api/process` as multipart form:
- `url` (optional YouTube URL)
- `file` (optional video upload)
- `clip_length` (10-60 seconds)
- `clip_count` (1-10)

Use either `url` or `file`. Results include clip URLs, thumbnail URL, hashtags, and subtitle status.
