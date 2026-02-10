---
name: RecapSource_Scout
description: Select a daily/weekly source video_id using YouTube Data API (or RSS+yt-dlp fallback) with backlog fallback.
---

## When To Use
Use when you need the system to pick "today's" recap candidate automatically (daily lane) or pick a "new release" style candidate (weekly lane).

## Inputs
- Optional: `queries[]`, `lookback_days`, `max_video_age_hours`, `min_views_per_hour`, `min_views_total`, `min_duration_seconds`
- Env: `YOUTUBE_API_KEY` (optional), `SCOUT_CHANNEL_IDS` (optional), `BACKLOG_VIDEO_IDS` (optional)

## Preconditions
- Runner is healthy: `GET http://localhost:8000/health`
- If using YouTube Data API scouting: `YOUTUBE_API_KEY` is set in `.env`
- If avoiding YouTube Data API: `SCOUT_CHANNEL_IDS` is set in `.env` (channel IDs, UC...)

## Steps
1. If `YOUTUBE_API_KEY` is set, call `POST /api/discover` with tuned thresholds and (optionally) a query list.
1. If `YOUTUBE_API_KEY` is NOT set but `SCOUT_CHANNEL_IDS` is set, call `POST /api/discover` (it will scout via RSS + yt-dlp metadata).
1. If discover returns an error or returns no `selected_video_id`, fall back to `BACKLOG_VIDEO_IDS`.
1. Persist the chosen `video_id` plus `selection_mode` in your orchestrator (n8n execution data).

## Acceptance Criteria
- A single `video_id` is selected.
- Selection reason is recorded (`selection_mode` or "backlog fallback").

## Verification
- `curl -fsS -X POST http://localhost:8000/api/discover -H 'Content-Type: application/json' -d '{"queries":["movie recap"],"top_n_channels":10,"videos_per_channel":5,"lookback_days":14,"max_video_age_hours":72,"min_views_per_hour":250,"min_views_total":20000,"min_duration_seconds":180}' | python3 -m json.tool`

## Failure Modes And Fallbacks
- YouTube API not configured or quota errors: set `SCOUT_CHANNEL_IDS` to use RSS, or use `BACKLOG_VIDEO_IDS` (manual curated list).
- No candidates pass thresholds: lower `min_views_per_hour` and/or increase `max_video_age_hours`, or use backlog.
- Ambiguous `video_id` input (URL pasted): extract ID from `watch?v=` or `youtu.be/`.

## Notes
- This is the "taste layer": the system uses views velocity and engagement proxies so you don't need manual taste.
