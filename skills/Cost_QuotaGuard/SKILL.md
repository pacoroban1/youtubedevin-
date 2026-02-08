---
name: Cost_QuotaGuard
description: Prevent runaway spend and quota lockouts by bounding candidates, retries, and schedule frequency.
---

## When To Use
Use before turning on 24/7 autopilot.

## Inputs
- Env knobs:
  - `SCRIPT_MAX_ATTEMPTS`
  - `auto_select_max_candidates` (pipeline request)
  - n8n schedule frequency

## Preconditions
- You know your daily budget target (UNKNOWN if not defined).

## Steps
1. Keep daily schedule to 1 run/day for the daily lane.
1. Bound auto-select candidates (e.g., max 3).
1. Keep script retries low (default 2).
1. Add health checks that do not call expensive endpoints.

## Acceptance Criteria
- The system cannot execute infinite retries or run every few minutes unintentionally.

## Verification
- Inspect n8n schedules and runner env defaults.

## Failure Modes And Fallbacks
- Quota hit mid-day: switch to backlog and skip expensive scout for that day.

