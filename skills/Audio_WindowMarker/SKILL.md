---
name: Audio_WindowMarker
description: Manually mark "movie audio moments" (smooth in/out) so the source audio only comes through at safe timestamps.
---

## When To Use
Use when you want to hear cast/ambience briefly, but keep the source narrator muted almost always.

## Inputs
- `video_id`
- A list of windows in narration-time seconds: `{start_time,end_time,fade_seconds,label}`

## Preconditions
- Runner uses `AUDIO_MIX_MODE=windows`
- Source audio is muted outside windows (`ORIG_AUDIO_DUCK_GAIN=0.0`)

## Steps
1. Render once with no windows (default).
1. Watch the render, note timestamps where you want original audio to breathe.
1. Set windows via API: `PUT /api/audio/windows/{video_id}`.
1. Re-render: `POST /api/render/{video_id}`.

## Acceptance Criteria
- English recap narrator is not heard outside your windows.
- Inside windows, audio fades smoothly (no hard cuts).

## Verification
- `curl -fsS -X PUT http://localhost:8000/api/audio/windows/$VIDEO_ID -H 'Content-Type: application/json' -d '{\"windows\":[{\"start_time\":62.4,\"end_time\":66.2,\"fade_seconds\":0.25,\"label\":\"cast line\"}]}' | python3 -m json.tool`
- `curl -fsS -X POST http://localhost:8000/api/render/$VIDEO_ID | python3 -m json.tool`

## Failure Modes And Fallbacks
- You still hear the source narrator inside a window: shorten/remove that window or lower `ORIG_AUDIO_FULL_GAIN`.
- You want zero source audio: set windows to `[]` and re-render.

## Notes
- For full autopilot later: add automatic VAD/diarization to propose windows (not implemented yet).

