---
name: RecapFactory Ops
description: Run local gates, freeze releases, promote/rollback to GCP, manage secrets safely, and keep the stack reachable via a minimal HTTPS gateway.
---

# RecapFactory Ops

Use this skill when hardening deployment and operational controls (not core media logic).

## Local_DoctorSmokeTest
Goal: prove the stack works locally before cloud.

Steps
1. Run `make gate-local`.
1. Optionally run pipeline with `VIDEO_ID=<id>` if OAuth is configured.

Acceptance criteria
- Ends with `LOCAL GATE PASSED`.

Verification
- `make gate-local`

## Release_TagFreeze
Goal: tag a known-good release.

Steps
1. `make release TAG=vX.Y.Z`

Acceptance criteria
- Tag exists locally and is pushed.

Verification
- `git tag --list | tail`

## Deploy_GCP
Goal: deploy tagged release to a single VM.

Steps
1. Use `infra/gcp/setup_vm.sh` once on the VM.
1. Use `make promote TAG=vX.Y.Z`.

Acceptance criteria
- Runner health is green on VM.

Verification
- `make gcp-health`

## Deploy_Rollback
Goal: roll back to a previous tag fast.

Steps
1. `make rollback`
1. Or `make rollback TAG=vX.Y.Z`

Acceptance criteria
- VM is running the target tag and services are healthy.

## Secrets_ConfigManager
Goal: never leak secrets; keep config repeatable.

Steps
1. Keep `.env` out of git.
1. Use `.env.example` as the only documented contract.
1. Ensure scripts never echo secrets.

Acceptance criteria
- No secrets printed in logs or committed.

## Gateway_ReverseProxyHTTPS
Goal: protect n8n UI and enable TLS.

Steps
1. Use `infra/gcp/docker-compose.caddy.yml` + basic auth.
1. If no domain: allow HTTP only and document limitation.

Acceptance criteria
- n8n UI requires auth.

## Cost_QuotaGuard
Goal: prevent runaway spend.

Steps
1. Bound retries in script generation and TTS.
1. Bound candidates in auto-select.
1. Prefer one run/day.

