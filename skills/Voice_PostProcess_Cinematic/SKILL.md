---
name: Voice_PostProcess_Cinematic
description: Apply optional cinematic narration processing (EQ + gentle compression + limiter + deeper tone) without breaking intelligibility.
---

## When To Use
Use when TTS is "too thin" or "too scared" and you want a deeper, tighter narrator sound.

## Inputs
- Path to a WAV (`tts_preview_*.wav` or `/api/media/audio/<video_id>/narration.wav`)

## Preconditions
- `ffmpeg` available on host (or inside runner container)

## Steps
1. Always start with previews first (`POST /api/tts_preview`).
1. Apply a safe processing chain (example):
1. Highpass (reduce rumble), lowpass (remove harshness), slight pitch-down, compressor, limiter.
1. If approved, apply to the final narration WAV and re-render video.

## Acceptance Criteria
- Processed audio sounds deeper/cleaner without distortion or pumping.

## Verification
- `ffprobe -v error -show_entries format=duration -of default=nw=1:nk=1 path/to/processed.wav`

## Failure Modes And Fallbacks
- Over-processing (robotic/muddy): reduce pitch shift and compressor makeup gain.
- Clipping: keep limiter at `0.98` and reduce overall gain.

## Notes
- This is intentionally optional. Keep a toggle (env) before baking into autopilot (UNKNOWN integration point).

