---
name: Orchestrator_ArtifactsPackager
description: Package final_video + narration + recap.md + thumbnails + metadata into a single dated folder for each run.
---

## When To Use
Use so every run leaves behind publish-ready artifacts even if upload fails.

## Inputs
- `video_id`
- Runner media URLs:
  - `/api/media/output/<video_id>/final_video.mp4`
  - `/api/media/audio/<video_id>/narration.wav`
  - `/api/media/output/<video_id>/recap.md`
  - `/api/media/thumbnails/<video_id>/...`

## Preconditions
- Render and thumbnail steps completed

## Steps
1. Create a host output folder: `outputs/<video_id>_<timestamp>/`.
1. Download core artifacts with `curl -fsS`.
1. Save runner JSON responses (ingest/script/voice/render/thumbnail) for audit/debug.

## Acceptance Criteria
- One folder contains everything needed to upload manually.

## Verification
- `ls -la outputs | head`

## Failure Modes And Fallbacks
- Media URL not found: verify runner static mount `app.mount("/api/media", ...)` and paths.
- Partial artifacts: still keep what exists and record missing items.

## Notes
- This is "unbreakable mode": never lose a day's work because upload broke.

