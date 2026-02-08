---
name: YouTube_UploadOAuth
description: Configure YouTube OAuth (client id/secret/refresh token) so the runner can upload videos automatically.
---

## When To Use
Use when you're ready for true autopilot uploads (no manual posting).

## Inputs
- Env (required):
  - `YOUTUBE_CLIENT_ID`
  - `YOUTUBE_CLIENT_SECRET`
  - `YOUTUBE_REFRESH_TOKEN`
- Optional:
  - `YOUTUBE_API_KEY` (for scouting)
  - `YOUTUBE_PRIVACY_STATUS` (`public|unlisted|private`)

## Preconditions
- You have valid OAuth credentials for the YouTube channel.
- Runner stack can be restarted safely.

## Steps
1. Put OAuth env vars into `.env` (do not print them in logs).
1. Restart stack: `docker compose up -d --build`.
1. Verify runner config reports OAuth configured.
1. Run a test upload on a known produced `video_id`.

## Acceptance Criteria
- `GET /api/config` shows `"oauth_configured": true`.
- `POST /api/upload/{video_id}` returns success and includes a YouTube URL.

## Verification
- `curl -fsS http://localhost:8000/api/config | python3 -m json.tool`
- `curl -fsS -X POST http://localhost:8000/api/upload/$VIDEO_ID | python3 -m json.tool`

## Failure Modes And Fallbacks
- OAuth init fails: refresh token revoked/expired; re-authorize and update refresh token.
- Upload fails mid-way: keep artifacts and upload manually (`Orchestrator_ArtifactsPackager`).

## Notes
- Secrets must never be committed. `.env` stays local/VM-only.

