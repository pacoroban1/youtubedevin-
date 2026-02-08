---
name: RecapSource_Ingest
description: Download the source video and produce a cleaned transcript (captions first, STT fallback).
---

## When To Use
Use when a `video_id` is selected and you need the video file + transcript in the runner DB/media store.

## Inputs
- `video_id`

## Preconditions
- Runner is healthy: `GET /health`
- `yt-dlp` + `ffmpeg` available inside runner container (covered by Dockerfile)

## Steps
1. Run ingest: `POST /api/ingest/{video_id}`.
1. Confirm response includes a non-empty `transcript_length` and a `source` of `youtube_captions`, `gemini`, or `whisper`.

## Acceptance Criteria
- Ingest endpoint returns `status=success`.
- Transcript is saved (downstream script generation does not error with missing transcript).

## Verification
- `curl -fsS -X POST http://localhost:8000/api/ingest/$VIDEO_ID | python3 -m json.tool`

## Failure Modes And Fallbacks
- Download timeout: retry once; if persistent, select another candidate.
- Transcript empty: ensure captions are attempted; otherwise ensure STT fallback works (`Transcript_STTFallback`).

## Notes
- This step creates/updates the `videos` row even when ingesting by ID directly (FK safety).

