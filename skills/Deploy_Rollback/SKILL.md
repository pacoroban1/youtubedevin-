---
name: Deploy_Rollback
description: Roll back the VM to the previous known-good tag quickly and safely.
---

## When To Use
Use when a promoted release breaks production.

## Inputs
- Optional `TAG` (explicit) or rollback to previous

## Preconditions
- VM reachable
- At least one previous tag deployed

## Steps
1. Roll back to previous: `make rollback`
1. Or roll back to explicit: `make rollback TAG=vX.Y.Z`
1. Re-run health checks.

## Acceptance Criteria
- Services healthy after rollback.

## Verification
- `make gcp-health`

