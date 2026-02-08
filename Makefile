.PHONY: up down build logs shell clean doctor run verify smoke gate-local release promote rollback gcp-health

COMPOSE ?= $(shell if command -v docker-compose >/dev/null 2>&1; then echo docker-compose; else echo "docker compose"; fi)

# Start services
up:
	$(COMPOSE) up -d

# Stop services
down:
	$(COMPOSE) down

# Build services
build:
	$(COMPOSE) build

# View logs
logs:
	$(COMPOSE) logs -f

# Shell into runner
shell:
	$(COMPOSE) exec runner bash

# Clean up volumes
clean:
	$(COMPOSE) down -v

# Check environment health
doctor:
	@echo "doctor: env"
	@if [ ! -f .env ]; then echo "missing: .env"; exit 1; fi
	@set -a; . ./.env >/dev/null 2>&1; set +a; \
		if [ -n "$$GEMINI_API_KEY" ]; then echo "set: GEMINI_API_KEY"; else echo "missing: GEMINI_API_KEY"; exit 1; fi
	@echo "doctor: docker"
	@docker info > /dev/null 2>&1 || (echo "missing: docker (not running)"; exit 1)
	@echo "ok: ready"

# Run everything (Postgres + N8N + Runner)
run: doctor
	$(COMPOSE) up -d --build
	@echo "🚀 Services started!"
	@echo "Runner: http://localhost:8000"
	@echo "N8N: http://localhost:5678"

# Fast local verifiers (no external API calls).
verify:
	@python3 -m compileall services/runner >/dev/null
	@for f in n8n/workflows/*.json; do python3 -m json.tool $$f >/dev/null; done
	@echo "ok: verify"

smoke: doctor
	@./scripts/smoke.sh

# Local acceptance gate (verify + doctor + smoke + runner health + optional full pipeline run)
gate-local:
	@bash scripts/gate_local.sh

# Freeze a known-good, locally-gated release tag and push it.
#
# Usage:
#   VIDEO_ID=... make release TAG=v1.0.0
release:
	@TAG="$(TAG)" bash scripts/release.sh

# Deploy a tag to your GCP VM (runs local gate unless SKIP_GATE=1).
#
# Required env:
#   GCP_PROJECT=... GCP_ZONE=... GCP_VM=...
promote:
	@bash -lc 'set -euo pipefail; if [[ "$${SKIP_GATE:-0}" != "1" ]]; then bash scripts/gate_local.sh; fi; bash infra/gcp/remote.sh promote --tag "$(TAG)"'

# Roll back to the previously deployed tag on the VM, or to an explicit TAG if provided.
rollback:
	@bash infra/gcp/remote.sh rollback $(if $(TAG),--tag $(TAG),)

# Remote healthcheck on the VM.
gcp-health:
	@bash infra/gcp/remote.sh health
