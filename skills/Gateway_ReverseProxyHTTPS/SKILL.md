---
name: Gateway_ReverseProxyHTTPS
description: Put n8n behind HTTPS + basic auth using a minimal reverse proxy (Caddy) on the VM.
---

## When To Use
Use for production VM so n8n UI isn't exposed on a raw port.

## Inputs
- `infra/gcp/docker-compose.caddy.yml`
- Env: `CADDY_SITE`, `CADDY_BASIC_AUTH_USER`, `CADDY_BASIC_AUTH_HASH`

## Preconditions
- VM has ports 80/443 open (or domain configured)

## Steps
1. Configure Caddy env vars in `.env` on VM.
1. Start proxy compose stack.
1. Verify n8n requires basic auth.

## Acceptance Criteria
- n8n UI is protected by auth and served via HTTPS (when domain is set).

## Verification
- Visit n8n URL in browser and confirm auth prompt.

## Failure Modes And Fallbacks
- No domain: run HTTP only and restrict IPs via firewall as a minimum.

