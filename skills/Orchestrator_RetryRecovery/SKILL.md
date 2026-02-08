---
name: Orchestrator_RetryRecovery
description: Add bounded retries and safe fallbacks per step so the daily run doesn't die on transient failures.
---

## When To Use
Use when you see intermittent failures (network, model timeouts, quotas).

## Inputs
- n8n retry settings (node-level)
- Runner bounded retry knobs:
  - `SCRIPT_MAX_ATTEMPTS`
  - Gemini retries in `gemini_client.py` (code)

## Preconditions
- You can tolerate "skip candidate and try next" behavior for scouting.

## Steps
1. In n8n, enable retries on HTTP nodes for 5xx/timeouts (bounded).
1. In runner, keep bounded attempts for script and TTS (already).
1. On hard blockers:
1. No captions + STT fails: skip candidate.
1. Upload fails: keep artifacts and report (manual intervention).

## Acceptance Criteria
- Transient failures retry and recover.
- Hard blockers fail fast with a clear error path.

## Verification
- Simulate a timeout by reducing node timeout and confirm retry behavior (n8n).
- Check daily report: `GET /api/report/daily`.

## Failure Modes And Fallbacks
- Infinite retries: enforce max attempts in n8n and runner.
- API quota exhaustion: shift to backlog lane for that day.

## Notes
- Recovery logic is where "scope creep" often sneaks in; keep it bounded and explicit.

