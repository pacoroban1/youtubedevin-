---
name: Orchestrator_HealthChecksAlerts
description: Monitor runner + n8n health and emit alerts when the daily machine is down or stalled.
---

## When To Use
Use once deployed to a VM so failures are caught without you checking manually.

## Inputs
- Runner health endpoints:
  - `GET /health`
  - `GET /api/report/daily`
- Alert channel credentials (UNKNOWN: Telegram/email/SMS)

## Preconditions
- A scheduler exists (n8n or cron)

## Steps
1. Schedule a periodic health workflow (e.g., hourly).
1. Call runner endpoints and fail workflow if not healthy.
1. On failure, send an alert containing request_id (if present) and timestamp.

## Acceptance Criteria
- Runner downtime triggers an alert within the check interval.

## Verification
- `curl -fsS http://localhost:8000/health`
- `curl -fsS http://localhost:8000/api/report/daily | python3 -m json.tool`

## Failure Modes And Fallbacks
- Alert channel missing creds: write to a persistent log or n8n error executions as fallback.

## Notes
- Keep alert payloads secret-free (never include `.env` values).

