---
name: Local_DoctorSmokeTest
description: Run local acceptance gates (verify/doctor/smoke/health) before promoting to cloud.
---

## When To Use
Use before every release tag and before deploying to a VM.

## Inputs
- Optional: `VIDEO_ID` for a full pipeline run (requires YouTube OAuth)

## Preconditions
- Docker daemon running
- `.env` exists with `GEMINI_API_KEY`

## Steps
1. Run `make gate-local`.
1. If OAuth is configured and you want end-to-end, run: `VIDEO_ID=<id> REQUIRE_PIPELINE=1 make gate-local`.

## Acceptance Criteria
- Ends with `LOCAL GATE PASSED`.

## Verification
- `make gate-local`

## Failure Modes And Fallbacks
- Gate fails at upload (missing OAuth): run without REQUIRE_PIPELINE or configure OAuth first.

## Notes
- This enforces "no cloud debugging".

