---
name: Thumb_TextOverlay_Amharic
description: Overlay large readable Amharic (Ethiopic) text on generated thumbnails using a proper Ethiopic font.
---

## When To Use
Use to ensure thumbnails have big Amharic hook text that reads on mobile.

## Inputs
- `video_id`
- Amharic hook text (derived from script hook)

## Preconditions
- Runner image includes an Ethiopic font (Noto Sans Ethiopic).
- Thumbnail images exist (`Thumb_Generation`).

## Steps
1. Verify Ethiopic font exists inside runner:
1. `/usr/share/fonts/truetype/noto/NotoSansEthiopic-Bold.ttf`
1. Generate thumbnails (overlay runs best-effort during generation when `hook_text` exists).
1. If overlay did not render correctly (missing glyphs/squares), fix fonts and rebuild runner image.

## Acceptance Criteria
- Thumbnail PNGs render Ethiopic characters correctly (not tofu squares).

## Verification
- `docker compose exec -T runner bash -lc 'ls -la /usr/share/fonts/truetype/noto/NotoSansEthiopic-Bold.ttf'`
- `curl -fsS -X POST http://localhost:8000/api/thumbnail/$VIDEO_ID | python3 -m json.tool`

## Failure Modes And Fallbacks
- Font missing: rebuild runner image after installing fonts (Dockerfile).
- Text too long: shorten overlay text or use 2-line layout (code change, optional).

## Notes
- Overlay is intentionally non-fatal; thumbnails should still generate if overlay fails.

