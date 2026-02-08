---
name: Transcript_STTFallback
description: Generate an English transcript via STT when captions are missing (Gemini first, Whisper fallback).
---

## When To Use
Use when captions are missing/empty or unreliable.

## Inputs
- `video_id`

## Preconditions
- `GEMINI_API_KEY` set for Gemini STT (recommended)
- Whisper python package available for local fallback inside runner

## Steps
1. Run ingest (`POST /api/ingest/{video_id}`).
1. Confirm `source` is `gemini` or `whisper` (not `failed`).
1. If `gemini` STT fails, ensure Whisper fallback produces non-empty text.

## Acceptance Criteria
- Transcript source is `gemini` or `whisper`.
- Transcript is non-empty and saved.

## Verification
- `curl -fsS -X POST http://localhost:8000/api/ingest/$VIDEO_ID | python3 -m json.tool`

## Failure Modes And Fallbacks
- Gemini STT blocked by tier/quota: Whisper fallback should run.
- Whisper fails (missing model/download): fix container deps or skip candidate.

## Notes
- Gemini STT uses Files API (better for large audio).

