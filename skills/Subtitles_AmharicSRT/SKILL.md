---
name: Subtitles_AmharicSRT
description: Generate Amharic subtitles (SRT) as a sidecar (optional) from script beats and narration duration.
---

## When To Use
Use when you want subtitles for accessibility/retention. This is optional and should never block render/upload.

## Inputs
- `video_id`
- Script beats (`full_script`) and narration duration

## Preconditions
- Script and narration exist

## Steps
1. Discovery: confirm whether subtitles are already generated for this video:
1. Check for `/api/media/output/<video_id>/subtitles.am.srt`.
1. If missing, implement a minimal generator:
1. Load beats from `full_script`.
1. Scale beat times to narration duration (same approach as audio-window scaling).
1. Write SRT to `/app/media/output/<video_id>/subtitles.am.srt`.
1. Keep subtitle generation best-effort and non-fatal.

## Acceptance Criteria
- SRT exists (when enabled) and has valid timecodes.

## Verification
- `curl -fsS http://localhost:8000/api/media/output/$VIDEO_ID/subtitles.am.srt | head -n 40`

## Failure Modes And Fallbacks
- Bad timestamps: regenerate using scaled beat end_time max as planned duration.
- If subtitles break render: keep subtitles as sidecar only (do not burn-in).

## Notes
- Not implemented as a first-class endpoint yet (requires small code add).

