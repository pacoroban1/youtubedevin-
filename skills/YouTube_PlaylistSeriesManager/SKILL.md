---
name: YouTube_PlaylistSeriesManager
description: Add uploads to playlists and manage a "series lane" so multi-part recaps stay organized.
---

## When To Use
Use when you want series behavior: playlist grouping + predictable cadence.

## Inputs
- Optional env: `YOUTUBE_PLAYLIST_ID`
- Series rules (UNKNOWN: how to detect series keys)

## Preconditions
- `YouTube_UploadOAuth` configured

## Steps
1. Ensure uploader can add uploads to a playlist:
1. Set `YOUTUBE_PLAYLIST_ID` to force a specific playlist, or let the runner auto-create one.
1. Define "series lane" rules (recommended):
1. Detect "Part 1/2/3" in generated titles.
1. Map series key -> playlist id.
1. If not implemented yet, keep playlist add best-effort and non-fatal.

## Acceptance Criteria
- Upload response includes `playlist_id` when playlist is configured or auto-created.

## Verification
- After upload: inspect returned `playlist_id` in `POST /api/upload/{video_id}` response.

## Failure Modes And Fallbacks
- Playlist operations fail due to permissions: continue upload without playlist and log warning.

## Notes
- Full "series scheduling" (auto schedule Part 2 tomorrow) is not implemented yet; do it via n8n as V2/V3.

