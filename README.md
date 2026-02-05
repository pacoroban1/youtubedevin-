# Amharic Recap Autopilot

An end-to-end YouTube automation system that discovers English recap videos, generates Amharic narration, and auto-uploads to YouTube with growth tracking.

## Architecture Overview

The system consists of 8 main modules orchestrated by n8n workflows:

1. **Channel Discovery (Part A)** - Finds top-performing recap channels using YouTube Data API
2. **Video Ingest (Part B)** - Downloads videos and extracts/generates transcripts
3. **Script Generation (Part C)** - Creates high-retention Amharic recap scripts via Gemini
4. **Voice Generation (Part D)** - Generates Amharic narration using Azure TTS (am-ET-AmehaNeural)
5. **Timing & Scene Match (Part E)** - Aligns narration to video scenes with forced alignment
6. **Thumbnail Generation (Part F)** - Creates thumbnails with Amharic hooks
7. **YouTube Upload (Part G)** - Uploads with optimized metadata, chapters, and playlists
8. **Growth Loop (Part H)** - Distributes to social platforms and tracks metrics

## Quick Start

### Prerequisites

- Docker and Docker Compose
- API keys for: YouTube Data API, Azure Speech Services, Google Gemini

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

4. Access the n8n dashboard at http://localhost:5678

### Environment Variables

See `.env.example` for all required variables:

| Variable | Description |
|----------|-------------|
| `YOUTUBE_CLIENT_ID` | YouTube OAuth client ID |
| `YOUTUBE_CLIENT_SECRET` | YouTube OAuth client secret |
| `YOUTUBE_REFRESH_TOKEN` | YouTube OAuth refresh token |
| `AZURE_SPEECH_KEY` | Azure Cognitive Services Speech key |
| `AZURE_SPEECH_REGION` | Azure region (e.g., eastus) |
| `GEMINI_API_KEY` | Google AI Studio API key |
| `POSTGRES_*` | PostgreSQL connection settings |
| `TELEGRAM_BOT_TOKEN` | (Optional) Telegram bot token for distribution |
| `TELEGRAM_CHANNEL_ID` | (Optional) Telegram channel ID |
| `TWITTER_*` | (Optional) Twitter API credentials |

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

PostgreSQL stores all pipeline data across 11 tables:

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

## TTS Voice Configuration

The system uses Microsoft Azure TTS with Amharic support:

- **Voice**: am-ET-AmehaNeural (male, deep narrator style)
- **Rate**: -5% (slightly slower for clarity)
- **Pitch**: -10% (deeper tone)
- **Loudness**: Normalized to -14 LUFS (YouTube standard)

Alternative voice: am-ET-MekdesNeural (female)

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
# Run tests
docker-compose exec runner pytest

# Test a specific module
docker-compose exec runner pytest tests/test_voice.py
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
├── docs/
│   ├── README.md
│   ├── pipeline.mmd       # Mermaid diagram
│   └── pipeline.png       # Rendered diagram
├── .env.example
└── Makefile
```

## License

MIT License
