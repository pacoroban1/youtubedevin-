---
name: Orchestrator_ScheduleRunner
description: Run the pipeline hands-free on daily and weekly schedules using n8n schedule triggers and runner endpoints.
---

## When To Use
Use when you want "one video per day" plus "one new-movie lane per week" without manual runs.

## Inputs
- n8n workflows:
  - `n8n/workflows/autopilot_daily_full_pipeline.json`
  - `n8n/workflows/autopilot_weekly_full_pipeline.json`
- Runner base URL (docker network): `http://runner:8000`

## Preconditions
- n8n is reachable: `http://localhost:5678`
- Runner is reachable from n8n: `http://runner:8000/health`

## Steps
1. Import the daily and weekly workflow JSON into n8n.
1. Verify HTTP Request nodes target `http://runner:8000` (not `localhost`).
1. Set schedule timing (interval or cron) per lane:
1. Daily: 24h cadence at your preferred time.
1. Weekly: 168h cadence (or cron weekly) with "new movie recap" queries.
1. Activate both workflows.

## Acceptance Criteria
- Daily workflow triggers and returns `status=success` (or a controlled error with a clear message).
- Weekly workflow triggers and uses its query list.

## Verification
- In n8n UI: run both workflows once manually.
- Runner: `curl -fsS http://localhost:8000/health`

## Failure Modes And Fallbacks
- If upload isn't configured yet, pipeline may fail at upload; ensure artifact packaging exists (`Orchestrator_ArtifactsPackager`).
- If YouTube API key isn't configured, scout will fall back to backlog if provided.

## Notes
- Keep "daily lane" and "weekly lane" separate so tuning one doesn't break the other.

