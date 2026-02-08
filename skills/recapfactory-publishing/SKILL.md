---
name: RecapFactory Publishing
description: Configure YouTube OAuth and publish rendered recap artifacts (upload, schedule, playlists/series) without leaking secrets.
---

# RecapFactory Publishing

Use this skill when you want true autopilot uploads to YouTube from the runner.

## YouTube_UploadOAuth
Goal: runner can upload via YouTube Data API using refresh token.

Inputs
- `YOUTUBE_CLIENT_ID`
- `YOUTUBE_CLIENT_SECRET`
- `YOUTUBE_REFRESH_TOKEN`
- Optional: `YOUTUBE_API_KEY`

Steps
1. Set env vars in `.env` on the host (never print them).
1. Restart stack: `docker compose up -d --build`
1. Verify config endpoint reports OAuth configured.

Acceptance criteria
- `GET /api/config` shows `"oauth_configured": true`.

Verification
- `curl -fsS http://localhost:8000/api/config | python3 -m json.tool`

## YouTube_PublishSchedule
Goal: schedule daily publish time (n8n or YouTube privacy settings).

Steps
1. Set default privacy: `YOUTUBE_PRIVACY_STATUS=public|unlisted|private`.
1. Prefer n8n to schedule runs at your desired time zone.

Acceptance criteria
- Upload endpoint succeeds for a test video.

Verification
- `curl -fsS -X POST http://localhost:8000/api/upload/$VIDEO_ID | python3 -m json.tool`

## YouTube_PlaylistSeriesManager
Goal: add uploads to the right playlist and manage series.

Steps
1. Implement playlist selection rules (by topic/series key) if not present yet.
1. Ensure playlist operations are best-effort and do not fail upload if playlist add fails.

Acceptance criteria
- Upload result includes `playlist_id` or logs a non-fatal playlist warning.

