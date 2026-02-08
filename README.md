# Amharic Recap Autopilot

An end-to-end YouTube automation system that discovers English recap videos, generates Amharic narration, and auto-uploads to YouTube with growth tracking.

## Architecture Overview

The system consists of 8 main modules orchestrated by n8n workflows:

1. **Channel Discovery (Part A)** - Finds top-performing recap channels using YouTube Data API
2. **Video Ingest (Part B)** - Downloads videos and extracts/generates transcripts
3. **Script Generation (Part C)** - Creates high-retention Amharic recap scripts via Gemini
4. **Voice Generation (Part D)** - Generates Amharic narration using Gemini TTS models
5. **Timing & Scene Match (Part E)** - Aligns narration to video scenes with forced alignment
6. **Thumbnail Generation (Part F)** - Creates thumbnails with Amharic hooks
7. **YouTube Upload (Part G)** - Uploads with optimized metadata, chapters, and playlists
8. **Growth Loop (Part H)** - Distributes to social platforms and tracks metrics

## Quick Start

### Prerequisites

- Docker and Docker Compose
- API keys for: YouTube Data API, Google Gemini

### Setup

1. Clone the repository:
```bash
git clone <repo-url>
cd amharic-recap-autopilot
```

2. Copy and configure environment variables:
```bash
cp .env.example .env
# Edit .env with your API keys
```

3. Start the services:
```bash
make up
```

4. Access:
   - n8n dashboard: http://localhost:5678
   - runner API: http://localhost:8000
   - UI dashboard: http://localhost:8000/ui

## Local→Cloud Promotion (GCP)

Deploy only **tagged, locally-gated** releases to a single always-on Compute Engine VM.

Full guide: `docs/DEPLOY_GCP.md`

### Local Gate

```bash
make gate-local
VIDEO_ID=YOUTUBE_VIDEO_ID make gate-local
```

### Release Freeze (Tag)

```bash
VIDEO_ID=YOUTUBE_VIDEO_ID make release TAG=v1.0.0
```

### Promote (Deploy Tag to VM)

```bash
export GCP_PROJECT="your-gcp-project-id"
export GCP_ZONE="us-central1-a"
export GCP_VM="your-vm-instance-name"

make promote TAG=v1.0.0
```

### Rollback

```bash
# Previous deployed tag (on the VM)
make rollback

# Explicit tag
make rollback TAG=v1.0.0
```

### Remote Health Check

```bash
make gcp-health
```

### Environment Variables

See `.env.example` for all required variables:

| Variable | Description |
|----------|-------------|
| `YOUTUBE_CLIENT_ID` | YouTube OAuth client ID |
| `YOUTUBE_CLIENT_SECRET` | YouTube OAuth client secret |
| `YOUTUBE_REFRESH_TOKEN` | YouTube OAuth refresh token |
| `AZURE_SPEECH_KEY` | (Legacy) Azure Speech key (not used in Gemini-only TTS) |
| `AZURE_SPEECH_REGION` | (Legacy) Azure region |
| `GEMINI_API_KEY` | Google AI Studio API key |
| `POSTGRES_*` | PostgreSQL connection settings |
| `TELEGRAM_BOT_TOKEN` | (Optional) Telegram bot token for distribution |
| `TELEGRAM_CHANNEL_ID` | (Optional) Telegram channel ID |
| `TWITTER_*` | (Optional) Twitter API credentials |
| `ZTHUMB_URL` | (Optional) ZThumb local thumbnail engine URL |
| `ALLOW_THUMBNAIL_FALLBACK_TO_OPENAI` | (Optional) Allow paid DALL·E fallback if ZThumb is configured but unavailable |
| `Z_LORA_PATH` | (Optional) ZThumb LoRA adapter path (inside ZThumb container) |
| `Z_LORA_SCALE` | (Optional) ZThumb LoRA scale (default recommended ~0.8) |

## Services

### Runner Service (FastAPI)

The runner service exposes REST APIs for each pipeline step:

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/api/discover` | POST | Discover top channels and videos |
| `/api/ingest/{video_id}` | POST | Download and transcribe video |
| `/api/script/{video_id}` | POST | Generate Amharic script |
| `/api/voice/{video_id}` | POST | Generate voice narration |
| `/api/render/{video_id}` | POST | Render final video |
| `/api/thumbnail/{video_id}` | POST | Generate thumbnails |
| `/api/upload/{video_id}` | POST | Upload to YouTube |
| `/api/distribute/{video_id}` | POST | Distribute to social platforms |
| `/api/report/daily` | GET | Generate daily report |
| `/api/config` | GET | Non-secret config summary for the UI |
| `/api/verify/voice` | GET | Verify voice support (am-ET) |
| `/api/verify/translate` | GET | Verify translation provider (optional) |
| `/api/verify/zthumb` | GET | Verify ZThumb connectivity from runner (optional) |
| `/api/jobs` | GET | List recent jobs (async runs) |
| `/api/jobs/{job_id}` | GET | Get a single job |
| `/api/jobs/pipeline/full` | POST | Start full pipeline as an async job (UI-friendly) |
| `/api/jobs/{job_id}/cancel` | POST | Best-effort cancel an in-flight job |
| `/api/pipeline/full` | POST | Run full pipeline synchronously (not recommended for UI) |

### n8n Workflows

Three main workflows are included:

1. **discovery.json** - Daily scheduled discovery of new channels/videos
2. **full_pipeline.json** - Complete video processing pipeline with quality gates
3. **daily_report.json** - Daily metrics aggregation and reporting

## Quality Gates

The system enforces quality at each step:

| Gate | Threshold | Action on Failure |
|------|-----------|-------------------|
| Script Quality | >= 90/100 | Regenerate script |
| Audio Quality | No clipping, -14 LUFS | Adjust and regenerate |
| Timing Alignment | >= 0.7 score | Compress/expand script |

## Database Schema

PostgreSQL stores all pipeline data across 12 tables:

- `channels` - Discovered YouTube channels
- `videos` - Target videos for processing
- `transcripts` - Raw and cleaned transcripts
- `scripts` - Generated Amharic scripts
- `audio` - Generated voice files
- `renders` - Final rendered videos
- `thumbnails` - Generated thumbnails
- `uploads` - YouTube upload records
- `metrics` - Performance metrics
- `ab_tests` - A/B test configurations
- `daily_reports` - Daily summary reports
- `jobs` - Long-running job state for UI polling/cancellation

## TTS Voice Configuration

The system uses Gemini TTS (see `services/runner/modules/voice.py`).

## Development

### Running Locally

```bash
# Start services
docker-compose up -d

# View logs
docker-compose logs -f runner

# Run a single video through the pipeline
curl -X POST http://localhost:8000/api/ingest/VIDEO_ID
```

### Testing

```bash
# Fast verifiers (syntax + workflow JSON)
make verify

# Smoke test (starts docker + checks runner health)
make smoke
```

## ZThumb Local Thumbnail Engine

The system includes a zero-setup local image generation engine for thumbnails:

### Starting ZThumb

```bash
cd zthumb
./run_zthumb.sh
```

Or with Docker Compose:
```bash
cd zthumb
docker compose up -d
```

### ZThumb API Endpoints

| Endpoint | Method | Description |
|----------|--------|-------------|
| `/health` | GET | Health check with GPU/VRAM info |
| `/models` | GET | List available models |
| `/generate` | POST | Generate thumbnail images |

### Example Usage

```bash
# Check health
curl http://localhost:8100/health

# Generate thumbnails
curl -X POST http://localhost:8100/generate \
  -H "Content-Type: application/json" \
  -d '{"prompt": "cinematic alien creature reveal", "batch": 4}'
```

### Integration with Autopilot

Set `ZTHUMB_URL=http://localhost:8100` in your `.env` file to use ZThumb for thumbnail generation instead of OpenAI DALL-E.
If you're running the runner via Docker (default), `localhost` inside the container is not your host. The runner will automatically retry common host aliases when it detects a localhost `ZTHUMB_URL`.
By default, if `ZTHUMB_URL` is set and ZThumb is down, thumbnail generation fails (so you can retry) instead of silently paying for DALL·E.
To opt into the paid fallback explicitly, set `ALLOW_THUMBNAIL_FALLBACK_TO_OPENAI=true`.

### LoRA Fine-Tune (Optional)

ZThumb can load a LoRA adapter at inference time:

```bash
export Z_LORA_PATH=/outputs/lora/zthumb_lora
export Z_LORA_SCALE=0.8
```

And you can run the end-to-end loop:

```bash
make train_lora
make eval_lora
make run_zthumb
make test_generate
```

#### Push-Button GPU Fine-Tune (Recommended)

For an “idiot-proof” pipeline tied to ZThumb inference, use:

```bash
# GPU-only (will fail loudly if no NVIDIA GPU is detected)
PRESET=quality make finetune_z
```

What it does:
- Prepares/validates the dataset (`datasets/thumbs/`)
- Downloads SDXL base with SHA verification
- Trains a LoRA (preset: `fast` or `quality`)
- Exports the adapter to `models/lora/<run_name>/`
- Validates the adapter by calling ZThumb `/generate` with `lora_scale=0` vs `0.8`
- Writes a report at `outputs/lora_eval/<run_name>/report.md` (with side-by-side images)

Cloud helpers:
- `scripts/cloud/runpod_train.sh` (run on the cloud GPU box after SSH)
- `scripts/cloud/fetch_artifact.sh` (pull the resulting `<run_name>.tar.gz` back to local)

Source of truth (base model + pinned trainer deps):
- `SOURCE_OF_TRUTH.md`

## Translation + Persona Recap (Optional)

By default, the script module uses Gemini to generate a high-retention Amharic recap directly.

If you want a more "structured" approach:
1. Generate short English beat recaps + emotion labels
2. Translate those beats using Google Cloud Translation API (paid) or LibreTranslate (open-source)
3. Run a final Gemini pass to apply narrator persona + cinematic emotion + `[PAUSE]` markers

Enable it by setting (if `GOOGLE_CLOUD_API_KEY` is set and `TRANSLATION_PROVIDER` is empty, it defaults to `google`):

```bash
export GOOGLE_CLOUD_API_KEY=...
export TRANSLATION_PROVIDER=google  # optional (auto-default)
export NARRATOR_PERSONA="futuristic captain"
export SCRIPT_BEAT_SECONDS=20
```

Or with LibreTranslate:

```bash
export LIBRETRANSLATE_URL=http://localhost:5000
export TRANSLATION_PROVIDER=libretranslate
export NARRATOR_PERSONA="futuristic captain"
export SCRIPT_BEAT_SECONDS=20
```

Verification endpoint:

```bash
curl http://localhost:8000/api/verify/translate
```

## File Structure

```
amharic-recap-autopilot/
├── docker-compose.yml
├── docker/
│   └── init.sql           # Database schema
├── n8n/
│   └── workflows/         # n8n workflow JSON exports
├── services/
│   └── runner/
│       ├── Dockerfile
│       ├── main.py        # FastAPI application
│       ├── requirements.txt
│       └── modules/       # Pipeline modules
│           ├── database.py
│           ├── discovery.py
│           ├── ingest.py
│           ├── script.py
│           ├── voice.py
│           ├── timing.py
│           ├── thumbnail.py
│           ├── upload.py
│           └── growth.py
├── zthumb/                 # Local thumbnail engine
│   ├── run_zthumb.sh      # One-command installer
│   ├── docker-compose.yml
│   ├── server/            # FastAPI server
│   ├── backends/          # Full/Turbo/GGUF backends
│   └── zthumb_client.py   # Python client & CLI
├── docs/
│   ├── README.md
│   ├── pipeline.mmd       # Mermaid diagram
│   └── pipeline.png       # Rendered diagram
├── .env.example
└── Makefile
```

## License

MIT License
