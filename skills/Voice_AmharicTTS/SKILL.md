---
name: Voice_AmharicTTS
description: Generate Amharic narration WAV from the structured script using Gemini TTS (with per-run voice override support).
---

## When To Use
Use after script generation to produce narration audio (`narration.wav`).

## Inputs
- `video_id`
- Optional query: `voice_name`
- Env: `GEMINI_API_KEY`, `GEMINI_TTS_VOICE_NAME`

## Preconditions
- Script exists (`POST /api/script/full/{video_id}`)
- `GEMINI_API_KEY` set

## Steps
1. Generate narration (force re-run when changing voice): `POST /api/voice/{video_id}?force=1&voice_name=<voice>`.
1. Confirm response includes `voice_id`, `audio_url`, and `narration_url`.

## Acceptance Criteria
- `/api/media/audio/<video_id>/narration.wav` exists and plays.
- Response `voice_id` matches the requested voice.

## Verification
- `curl -fsS -X POST "http://localhost:8000/api/voice/$VIDEO_ID?force=1&voice_name=Charon" | python3 -m json.tool`

## Failure Modes And Fallbacks
- Gemini TTS not enabled for key/tier: switch key/tier or fall back to another voice provider (UNKNOWN).
- TTS timeouts: reduce script length or increase service timeouts (code/env change).

## Notes
- The runner wraps raw PCM into WAV reliably (prevents "awful audio" corruption).

