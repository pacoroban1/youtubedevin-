---
name: Meta_TitleDescTags
description: Generate Amharic title/description/tags for the upload (Gemini-assisted) and keep them with the artifacts.
---

## When To Use
Use before upload so every video ships with SEO-ready metadata (even if upload fails).

## Inputs
- `video_id`
- Script hook + recap text
- Env: `GEMINI_API_KEY`

## Preconditions
- Script exists (for hook/summary)

## Steps
1. If YouTube upload is enabled, metadata is generated inside the upload step automatically.
1. If upload is not enabled yet, implement a "metadata-only" artifact writer (recommended):
1. Write `title.txt`, `description.txt`, `tags.json` to `/app/media/output/<video_id>/`.

## Acceptance Criteria
- Metadata exists either in upload record (DB) or as artifact files.

## Verification
- If upload is enabled: run `POST /api/upload/{video_id}` and inspect response fields.
- If artifact mode implemented: `curl -fsS http://localhost:8000/api/media/output/$VIDEO_ID/title.txt | head`

## Failure Modes And Fallbacks
- Gemini errors: fall back to a safe template title/description (already exists in uploader fallback titles).

## Notes
- This skill is a "gap filler" for the case where upload is temporarily disabled but you still want publish-ready assets.

