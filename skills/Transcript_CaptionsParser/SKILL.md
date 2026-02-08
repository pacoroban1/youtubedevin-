---
name: Transcript_CaptionsParser
description: Extract an English transcript from YouTube captions/subtitles (preferred path).
---

## When To Use
Use when you want maximum accuracy/cheap ingest by using captions instead of ASR.

## Inputs
- `video_id`
- Desired caption language (currently hard-coded to `en` auto-subs in ingest)

## Preconditions
- `yt-dlp` available in runner container
- Source video has captions/auto-subs

## Steps
1. Run ingest (`POST /api/ingest/{video_id}`).
1. Confirm ingest reports `"source": "youtube_captions"`.
1. If you need different caption languages, modify ingest caption settings and re-run.

## Acceptance Criteria
- Transcript source is `youtube_captions`.
- Transcript is non-empty.

## Verification
- `curl -fsS -X POST http://localhost:8000/api/ingest/$VIDEO_ID | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get(\"status\")==\"success\"; print(d.get(\"source\"))'`

## Failure Modes And Fallbacks
- No caption file produced: fall back to `Transcript_STTFallback`.
- Captions exist but wrong language: update ingest subtitle language handling (UNKNOWN if needed).

## Notes
- Captions are parsed from yt-dlp `json3` events into a single transcript string.

