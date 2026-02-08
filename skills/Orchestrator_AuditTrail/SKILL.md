---
name: Orchestrator_AuditTrail
description: Ensure each run is traceable: selected source, steps executed, artifacts produced, and failures with request_id.
---

## When To Use
Use when you want confidence and debuggability (what ran, why, and what broke).

## Inputs
- Runner responses (JSON) and headers (`X-Request-ID`)
- n8n execution data
- DB job records (`/api/jobs/*`)

## Preconditions
- You store artifacts per run (`Orchestrator_ArtifactsPackager`)

## Steps
1. Save runner JSON responses per step into the artifact folder.
1. Save `selected_video_id`, `selection_mode`, and thresholds from discover snapshot.
1. If a step fails, capture `request_id` from JSON error payload and include in alert.

## Acceptance Criteria
- For any day, you can locate:
  - source `video_id`
  - final output path
  - failure reason (if any)

## Verification
- `curl -fsS http://localhost:8000/api/report/daily | python3 -m json.tool`

## Failure Modes And Fallbacks
- Missing request_id on non-error responses: use timestamps + job_id as correlation IDs.

## Notes
- Audit trail is what keeps the "WAR MACHINE" from becoming a mystery box.

