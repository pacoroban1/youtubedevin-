.PHONY: up down build logs shell clean doctor run

# Start services
up:
	docker-compose up -d

# Stop services
down:
	docker-compose down

# Build services
build:
	docker-compose build

# View logs
logs:
	docker-compose logs -f

# Shell into runner
shell:
	docker-compose exec runner bash

# Clean up volumes
clean:
	docker-compose down -v

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
	docker-compose up -d --build
	@echo "🚀 Services started!"
	@echo "Runner: http://localhost:8000"
	@echo "N8N: http://localhost:5678"
