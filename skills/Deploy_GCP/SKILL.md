---
name: Deploy_GCP
description: Promote a tagged release to a single always-on GCP Compute Engine VM running docker compose 24/7.
---

## When To Use
Use when local gate is green and you want "always-on autopilot" using your Google credits.

## Inputs
- Env: `GCP_PROJECT`, `GCP_ZONE`, `GCP_VM`
- `TAG`

## Preconditions
- VM provisioned (Ubuntu 22.04 recommended)
- VM setup ran once: `infra/gcp/setup_vm.sh`

## Steps
1. Run: `make promote TAG=vX.Y.Z`.
1. Confirm services are up and healthy.

## Acceptance Criteria
- Runner health OK on VM.
- n8n reachable (prefer behind proxy + auth).

## Verification
- `make gcp-health`

## Failure Modes And Fallbacks
- SSH/permissions issues: verify gcloud auth and firewall rules.
- VM too small: upgrade to `e2-medium`.

