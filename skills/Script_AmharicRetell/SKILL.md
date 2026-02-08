---
name: Script_AmharicRetell
description: Generate a structured Amharic recap script (transformative retelling, not literal translation) with beats and timing.
---

## When To Use
Use after ingest to produce the Amharic narration plan (hook + beats + payoff + CTA).

## Inputs
- `video_id`
- Env knobs: `NARRATOR_PERSONA`, `SCRIPT_BEAT_SECONDS`, `SCRIPT_MAX_BEATS`

## Preconditions
- Transcript exists for `video_id` (ingest completed)
- `GEMINI_API_KEY` set

## Steps
1. Generate full structured script: `POST /api/script/full/{video_id}?force=1`.
1. Confirm output includes: `hook`, `beats[]`, `payoff`, `cta`, `quality_score`.
1. Fetch `recap.md` artifact for timestamped recap.

## Acceptance Criteria
- Script stored and subsequent TTS does not error with missing script.
- `recap.md` exists at `/api/media/output/<video_id>/recap.md`.

## Verification
- `curl -fsS -X POST "http://localhost:8000/api/script/full/$VIDEO_ID?force=1" | python3 -m json.tool`
- `curl -fsS http://localhost:8000/api/media/output/$VIDEO_ID/recap.md | head -n 40`

## Failure Modes And Fallbacks
- Script too literal/flat: raise `SCRIPT_MAX_ATTEMPTS` and tune `SCRIPT_QUALITY_MIN` (`Script_QualityGateLoop`).
- Script contains too much Latin text: adjust prompt/persona or reject candidate.

## Notes
- The script is the "brain" of the pipeline. Downstream voice/render/thumbnail all depend on it.

