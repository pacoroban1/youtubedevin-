---
name: RecapFactory Core Production
description: Run the core "one video in -> Amharic recap out" production steps (scout/ingest/transcript/script/voice/audio windows/render/subtitles/thumbnail/metadata) using the local runner API and repo tooling.
---

# RecapFactory Core Production

Use this skill when you want to produce an Amharic recap artifact set from a target video, or implement/fix the core production subsystems.

Repo context (assumed)
1. Runner API at `http://localhost:8000`
1. Media root in runner container at `/app/media`
1. Outputs exported to host under `outputs/`

## Subskills (Names + What "Done" Means)

## RecapSource_Scout
Goal: pick a candidate `video_id` to run today.

Steps
1. If YouTube API creds exist: call `POST /api/discover` with queries and thresholds.
1. If not: use `BACKLOG_VIDEO_IDS` fallback (or a user-provided URL) and extract `video_id`.

Acceptance criteria
- A single `video_id` is selected and logged.

Verification
- `curl -fsS http://localhost:8000/api/discover | python3 -m json.tool`

## RecapSource_Ingest
Goal: download source video and extract a clean transcript.

Steps
1. Run ingest for chosen `video_id`.
1. Confirm transcript exists in DB via subsequent script generation (or inspect runner logs on failure).

Acceptance criteria
- `POST /api/ingest/{video_id}` returns success.

Verification
- `curl -fsS -X POST http://localhost:8000/api/ingest/$VIDEO_ID | python3 -m json.tool`

## Transcript_CaptionsParser
Goal: prefer captions/subtitles when available.

Steps
1. Ensure ingest path tries captions first (do not regress into "always ASR").
1. Add a small regression check: ingest completes without invoking ASR when captions exist (best-effort; depends on source).

Acceptance criteria
- Ingest output indicates captions path when available (or logs show captions fetched).

Verification
- Run `POST /api/ingest/{video_id}` on a video known to have captions and inspect logs.

## Transcript_STTFallback
Goal: if captions are missing, fall back to speech-to-text.

Steps
1. Ensure ingest has an ASR fallback path and doesn't crash on missing captions.

Acceptance criteria
- Ingest succeeds on a video without captions.

Verification
- `curl -fsS -X POST http://localhost:8000/api/ingest/$VIDEO_ID | python3 -m json.tool`

## Script_AmharicRetell
Goal: produce a structured Amharic retelling (transformative, not literal).

Steps
1. Call `POST /api/script/full/{video_id}?force=1`.
1. Confirm response includes `hook`, `beats[]`, `payoff`, `cta`.

Acceptance criteria
- Script JSON exists and is stored in DB.
- `recap.md` is generated under `/api/media/output/<video_id>/recap.md`.

Verification
- `curl -fsS -X POST "http://localhost:8000/api/script/full/$VIDEO_ID?force=1" | python3 -m json.tool`
- `curl -fsS http://localhost:8000/api/media/output/$VIDEO_ID/recap.md | head`

## Script_QualityGateLoop
Goal: bounded retries to avoid flat/literal output.

Steps
1. Keep retries bounded by env (`SCRIPT_MAX_ATTEMPTS`) to control spend.
1. Enforce cheap local heuristics: non-empty beats, quality_score, low Latin ratio for Amharic.

Acceptance criteria
- Script generation returns with `quality_score` present.
- No infinite loops.

Verification
- `curl -fsS -X POST "http://localhost:8000/api/script/full/$VIDEO_ID?force=1" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert d.get(\"quality_score\") is not None'`

## Voice_PersonaSelector
Goal: pick a stable narrator voice.

Steps
1. List available voices: `GET /api/tts/voices`.
1. Generate short previews: `POST /api/tts_preview`.
1. Decide a default (`GEMINI_TTS_VOICE_NAME`) and optionally override per run (`voice_name`).

Acceptance criteria
- A chosen voice name is documented (Charon/Fenrir/etc).

Verification
- `curl -fsS http://localhost:8000/api/tts/voices | python3 -m json.tool`

## Voice_AmharicTTS
Goal: generate narration WAV for a video.

Steps
1. Generate narration: `POST /api/voice/{video_id}?force=1&voice_name=<voice>`.
1. Confirm `voice_id` and URLs returned.

Acceptance criteria
- `narration.wav` exists at `/api/media/audio/<video_id>/narration.wav`.

Verification
- `curl -fsS -X POST "http://localhost:8000/api/voice/$VIDEO_ID?force=1&voice_name=Charon" | python3 -m json.tool`

## Voice_PostProcess_Cinematic
Goal: optional "deeper / tighter / cinematic" processing.

Steps
1. Start with preview-only processing on `tts_preview_*.wav`.
1. If approved, apply the same filter chain to the final narration stage (do not bake this in until user signs off).

Acceptance criteria
- Processed preview WAVs exist and are listenable.

Verification
- `ls -la outputs | rg tts_preview_.*_cinematic\\.wav || true`

## Audio_WindowMarker
Goal: allow brief "movie audio moments" while keeping source narration muted.

Steps
1. Default to no windows.
1. When needed, set windows explicitly via `PUT /api/audio/windows/{video_id}` using narration-time seconds.
1. Re-render after changes.

Acceptance criteria
- Override file exists at `/api/media/output/<video_id>/audio_windows.override.json`.

Verification
- `curl -fsS -X PUT http://localhost:8000/api/audio/windows/$VIDEO_ID -H 'Content-Type: application/json' -d '{\"windows\":[]}' | python3 -m json.tool`

## Video_RenderAndMix
Goal: render `final_video.mp4` with narration, with source audio muted except optional windows.

Steps
1. Render: `POST /api/render/{video_id}`.
1. If render fails, inspect stderr in runner logs and rerun.

Acceptance criteria
- `final_video.mp4` exists at `/api/media/output/<video_id>/final_video.mp4`.

Verification
- `curl -fsS -X POST http://localhost:8000/api/render/$VIDEO_ID | python3 -m json.tool`

## Subtitles_AmharicSRT
Goal: generate Amharic subtitles (SRT) aligned to narration.

Steps
1. If no subsystem exists yet: implement as a separate module and write to `/app/media/output/<video_id>/subtitles.am.srt`.
1. Keep it optional and never break render when subtitle generation fails.

Acceptance criteria
- SRT file exists (when enabled).

Verification
- `curl -fsS -I http://localhost:8000/api/media/output/$VIDEO_ID/subtitles.am.srt || true`

## Thumb_Generation
Goal: generate multiple thumbnails.

Steps
1. Run: `POST /api/thumbnail/{video_id}`.
1. Ensure images are saved under `/app/media/thumbnails/<video_id>/`.

Acceptance criteria
- At least 1 thumbnail exists and is recorded in DB.

Verification
- `curl -fsS -X POST http://localhost:8000/api/thumbnail/$VIDEO_ID | python3 -m json.tool`

## Thumb_TextOverlay_Amharic
Goal: overlay large, readable Amharic text.

Steps
1. If implemented in generator: ensure font supports Ethiopic and is readable at mobile sizes.
1. If not implemented: treat as a follow-on module to produce `thumb_final.png`.

Acceptance criteria
- Exported thumbnail with Amharic overlay exists.

Verification
- `ls -la outputs | rg 'thumb_.*\\.png' || true`

## Meta_TitleDescTags
Goal: generate title/description/tags for upload.

Steps
1. If upload enabled: metadata is generated as part of upload module.
1. If upload not enabled: write `title.txt`, `description.txt`, `tags.json` under `/app/media/output/<video_id>/`.

Acceptance criteria
- Metadata artifacts exist (even if upload is disabled).

Verification
- `curl -fsS http://localhost:8000/api/media/output/$VIDEO_ID/recap.md | head`

## Verification Bundle (Core)
Run these when changing core production modules.
1. `make verify`
1. `make smoke`
1. `VIDEO_ID=<id> make gate-local`

