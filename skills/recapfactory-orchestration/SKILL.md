---
name: RecapFactory Orchestration
description: Make the recap pipeline run hands-free with scheduling, retries, artifact packaging, health checks, and an audit trail using n8n + runner endpoints.
---

# RecapFactory Orchestration

Use this skill to run the system daily/weekly without babysitting, and to harden “ops” behavior without changing core pipeline logic.

Assumptions
1. Runner API is reachable from n8n using the docker service name: `http://runner:8000`
1. Workflows exist at `n8n/workflows/autopilot_daily_full_pipeline.json` and `n8n/workflows/autopilot_weekly_full_pipeline.json`

## Orchestrator_ScheduleRunner
Goal: daily and weekly triggers call the runner pipeline.

Steps
1. Import workflow JSONs into n8n.
1. Ensure all runner HTTP nodes use `http://runner:8000` (not localhost).
1. Activate daily and weekly workflows.

Acceptance criteria
- n8n workflows are active and execute on schedule.

Verification
- n8n UI reachable at `http://localhost:5678`
- Runner health: `curl -fsS http://localhost:8000/health`

## Orchestrator_JobQueue
Goal: avoid overlapping runs and allow cancellation.

Steps
1. Prefer async jobs via `POST /api/jobs/pipeline/full` when n8n supports polling.
1. Store `job_id` in n8n execution context.
1. Poll `GET /api/jobs/{job_id}` until succeeded/failed.
1. On timeout, call `POST /api/jobs/{job_id}/cancel`.

Acceptance criteria
- A job can be started, observed, and canceled.

Verification
- `curl -fsS -X POST http://localhost:8000/api/jobs/pipeline/full -H 'Content-Type: application/json' -d '{"auto_select":false,"video_id":"wniqD-bB7CM"}' | python3 -m json.tool`

## Orchestrator_RetryRecovery
Goal: retry safe steps, fail fast on hard blockers.

Steps
1. Use bounded retries in n8n for transient errors (network, 5xx, timeouts).
1. If upload fails due to missing OAuth, mark run as “produced but not uploaded” and exit cleanly.
1. Do not loop endlessly.

Acceptance criteria
- Failures produce actionable error output without repeated infinite runs.

Verification
- `curl -fsS http://localhost:8000/api/report/daily | python3 -m json.tool`

## Orchestrator_ArtifactsPackager
Goal: on each run, keep a single folder with everything needed to publish manually.

Steps
1. After render/thumbnail (even if upload fails), fetch:
1. `/api/media/output/<video_id>/final_video.mp4`
1. `/api/media/audio/<video_id>/narration.wav`
1. `/api/media/output/<video_id>/recap.md`
1. Any thumbnails under `/api/media/thumbnails/<video_id>/` (if exposed) or from runner response.
1. Save into `outputs/<video_id>_<timestamp>/` on the host (n8n can write to a mounted volume, or runner can expose a packager endpoint later).

Acceptance criteria
- A single artifact directory exists per run.

Verification
- `ls -la outputs | head`

## Orchestrator_HealthChecksAlerts
Goal: detect failures early and notify.

Steps
1. Health endpoints:
1. `GET /health`
1. `GET /api/report/daily`
1. Add n8n check workflow that runs every hour.
1. On failure, send a message (Telegram/email/etc) with request_id and error.

Acceptance criteria
- Health check workflow flags runner down within 1 hour.

Verification
- `curl -fsS http://localhost:8000/health`
- `curl -fsS http://localhost:8000/api/report/daily | python3 -m json.tool`

## Orchestrator_AuditTrail
Goal: every run is traceable.

Steps
1. Ensure runner responses include `X-Request-ID` and error payload includes `request_id`.
1. n8n must store `video_id`, `job_id`, timestamps, and final status.
1. Do not log secrets.

Acceptance criteria
- You can answer: what ran, when, what video, what failed, and where artifacts are.

Verification
- Inspect runner JSON responses for `request_id` (errors) and `X-Request-ID` header.

## Verification Bundle (Orchestration)
1. `make smoke`
1. Trigger one daily workflow manually in n8n and verify it reaches runner.

