---
name: Thumb_Generation
description: Generate 4 high-contrast 16:9 thumbnails with Gemini/Imagen fallback and pick a best candidate.
---

## When To Use
Use after script generation (hook text helps) to generate thumbnails for upload.

## Inputs
- `video_id`
- `GEMINI_API_KEY`

## Preconditions
- Script exists (recommended; hook improves prompt conditioning)
- Gemini image generation enabled for key/tier

## Steps
1. Call `POST /api/thumbnail/{video_id}`.
1. Confirm response includes `images[]` with `url` fields.
1. Pick the `selected_path` (best heuristic score) or override manually.

## Acceptance Criteria
- At least 1 thumbnail PNG exists under `/api/media/thumbnails/<video_id>/`.

## Verification
- `curl -fsS -X POST http://localhost:8000/api/thumbnail/$VIDEO_ID | python3 -m json.tool`

## Failure Modes And Fallbacks
- Imagen/T2I not enabled: fix key/tier or use `ZTHUMB_URL` (optional external service).
- Overlay fails: generation must still succeed (overlay is best-effort).

## Notes
- Generation prompt requests "no text", then overlay is applied after generation for reliability.

