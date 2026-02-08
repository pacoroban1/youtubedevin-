---
name: Script_QualityGateLoop
description: Tune and enforce a bounded script quality loop (high-energy Amharic, low literalness) without runaway spend.
---

## When To Use
Use when scripts come out flat/literal, not "high retention", or contain too much English/Latin.

## Inputs
- Env: `SCRIPT_QUALITY_MIN`, `SCRIPT_MAX_ATTEMPTS`, `NARRATOR_PERSONA`

## Preconditions
- `GEMINI_API_KEY` set

## Steps
1. Set bounds: `SCRIPT_MAX_ATTEMPTS` (keep small; default 2).
1. Set minimum bar: `SCRIPT_QUALITY_MIN` (e.g. 0.85-0.92).
1. Re-run: `POST /api/script/full/{video_id}?force=1`.
1. If still weak, adjust `NARRATOR_PERSONA` to match your channel energy, and re-run.

## Acceptance Criteria
- Script returns with `quality_score >= SCRIPT_QUALITY_MIN` (best-effort).
- No infinite retries (bounded attempts).

## Verification
- `curl -fsS -X POST "http://localhost:8000/api/script/full/$VIDEO_ID?force=1" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(\"quality_score=\", d.get(\"quality_score\"))'`

## Failure Modes And Fallbacks
- Gemini JSON schema failures: lower strictness by reducing `SCRIPT_MAX_BEATS` or shortening transcript context (code change).
- If repeated failures: accept a simpler "straight recap" style for that run and move on.

## Notes
- This is where you iterate "Fantastic Captain energy" without ballooning the whole project.

