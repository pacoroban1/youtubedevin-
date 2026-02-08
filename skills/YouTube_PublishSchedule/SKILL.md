---
name: YouTube_PublishSchedule
description: Control publish timing and privacy via n8n schedules and YouTube privacy settings.
---

## When To Use
Use when you want daily uploads at a consistent time and weekly "new movie" lane scheduling.

## Inputs
- n8n schedule configuration
- Env: `TIMEZONE`, `YOUTUBE_PRIVACY_STATUS`

## Preconditions
- `YouTube_UploadOAuth` configured
- n8n running and reachable

## Steps
1. Set the daily workflow schedule to your desired publish time.
1. Set weekly workflow schedule for the "new movie lane".
1. Use `YOUTUBE_PRIVACY_STATUS=private` for review-first flows, then flip to `public` later.

## Acceptance Criteria
- Daily run starts on schedule and uploads successfully.
- Weekly run starts on schedule and uploads successfully.

## Verification
- Trigger n8n workflows manually once and confirm upload returns YouTube URL.

## Failure Modes And Fallbacks
- If scheduling needs exact wall-clock times, replace "interval hours" with cron (n8n change).

## Notes
- This project schedules the run; YouTube API scheduling fields are not implemented here (UNKNOWN).

