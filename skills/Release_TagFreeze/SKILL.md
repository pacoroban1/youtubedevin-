---
name: Release_TagFreeze
description: Freeze a known-good local build into an immutable git tag for promotion to cloud.
---

## When To Use
Use after local gate passes and you want a deployable release artifact.

## Inputs
- `TAG` (e.g., `v1.0.0`)

## Preconditions
- Local gate passes (`Local_DoctorSmokeTest`)
- Git remote configured

## Steps
1. Run: `make release TAG=vX.Y.Z`.
1. Confirm tag exists and is pushed.

## Acceptance Criteria
- Tag exists locally and in remote.

## Verification
- `git tag --list | tail`
- `git ls-remote --tags origin | tail`

## Failure Modes And Fallbacks
- Dirty git tree blocks release: commit or stash changes before tagging.

