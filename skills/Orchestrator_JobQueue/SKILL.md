---
name: Orchestrator_JobQueue
description: Run pipeline as an async job with polling and cancellation to prevent overlapping daily runs.
---

## When To Use
Use when you need job-level control (poll status, avoid overlaps, cancel stuck runs).

## Inputs
- Runner jobs endpoints:
  - `POST /api/jobs/pipeline/full`
  - `GET /api/jobs/{job_id}`
  - `POST /api/jobs/{job_id}/cancel`

## Preconditions
- Runner healthy

## Steps
1. Start a job: `POST /api/jobs/pipeline/full`.
1. Poll `GET /api/jobs/{job_id}` until `status` is `succeeded` or `failed`.
1. If the job exceeds a wall-clock timeout, call cancel.

## Acceptance Criteria
- A job progresses through steps and ends in a terminal state.
- Cancellation works for hung jobs.

## Verification
- `curl -fsS -X POST http://localhost:8000/api/jobs/pipeline/full -H 'Content-Type: application/json' -d '{"auto_select":false,"video_id":"wniqD-bB7CM"}' | python3 -m json.tool`

## Failure Modes And Fallbacks
- Runner restart loses in-memory task handles: rely on DB job status and prevent overlap at scheduler level.

## Notes
- Prefer this mode for "unbreakable autopilot" because it's observable and controllable.

