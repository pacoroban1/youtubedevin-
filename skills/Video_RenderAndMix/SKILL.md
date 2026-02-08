---
name: Video_RenderAndMix
description: Render final video with narration and strict source-audio muting (optional windows), producing /api/media/output/<video_id>/final_video.mp4.
---

## When To Use
Use after narration is generated to render a final upload-ready MP4.

## Inputs
- `video_id`
- Env knobs: `AUDIO_MIX_MODE`, `ORIG_AUDIO_DUCK_GAIN`, `ORIG_AUDIO_FULL_GAIN`, `NARRATION_GAIN`, `NARRATION_DUCK_GAIN`

## Preconditions
- Source video exists (ingest complete)
- Narration exists (`Voice_AmharicTTS` complete)
- `ffmpeg` available in runner container

## Steps
1. Render: `POST /api/render/{video_id}`.
1. Confirm output is written to `/api/media/output/<video_id>/final_video.mp4`.
1. If you need source-audio windows, set them first (`Audio_WindowMarker`) then re-render.

## Acceptance Criteria
- Render endpoint returns `status=success`.
- Output MP4 exists and plays.
- Source audio is muted except explicit windows.

## Verification
- `curl -fsS -X POST http://localhost:8000/api/render/$VIDEO_ID | python3 -m json.tool`
- `curl -fsS -I http://localhost:8000/api/media/output/$VIDEO_ID/final_video.mp4 | head -n 1`

## Failure Modes And Fallbacks
- Mixed render fails (missing audio stream): renderer falls back to replace mode automatically.
- You still hear source narrator: ensure `ORIG_AUDIO_DUCK_GAIN=0.0` and windows are empty or safe.

## Notes
- Use `AUDIO_MIX_MODE=replace` if you want guaranteed zero source audio.

