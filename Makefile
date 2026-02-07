.PHONY: up down logs build clean test shell zthumb-up zthumb-down smoke run_zthumb train_lora eval_lora test_generate

# Start all services
up:
	docker-compose up -d
	@echo "Services started!"
	@echo "n8n dashboard: http://localhost:5678"
	@echo "Runner API: http://localhost:8000"
	@echo "PostgreSQL: localhost:5432"

# Stop all services
down:
	docker-compose down

# View logs
logs:
	docker-compose logs -f

# View specific service logs
logs-runner:
	docker-compose logs -f runner

logs-n8n:
	docker-compose logs -f n8n

logs-postgres:
	docker-compose logs -f postgres

# Build images
build:
	docker-compose build

# Rebuild and start
rebuild: build up

# Clean up volumes and images
clean:
	docker-compose down -v --rmi local
	rm -rf media/

# Run tests
test:
	docker-compose exec runner python -m unittest discover -s tests -p 'test_*.py'

# Shell into runner container
shell:
	docker-compose exec runner /bin/bash

# Initialize database (run after first start)
init-db:
	docker-compose exec postgres psql -U autopilot -d amharic_recap -f /docker-entrypoint-initdb.d/init.sql

# Run discovery manually
discover:
	curl -X POST http://localhost:8000/api/discover \
		-H "Content-Type: application/json" \
		-d '{"queries": ["movie recap", "story recap"], "top_n_channels": 10, "videos_per_channel": 5}'

# Process a single video (usage: make process VIDEO_ID=abc123)
process:
	@if [ -z "$(VIDEO_ID)" ]; then echo "Usage: make process VIDEO_ID=abc123"; exit 1; fi
	curl -X POST http://localhost:8000/api/ingest/$(VIDEO_ID)

# Generate daily report
report:
	curl -X GET http://localhost:8000/api/report/daily

# Health check
health:
	@echo "Checking services..."
	@curl -s http://localhost:8000/health || echo "Runner: DOWN"
	@curl -s http://localhost:5678/healthz || echo "n8n: DOWN"
	@docker-compose exec postgres pg_isready -U autopilot || echo "PostgreSQL: DOWN"

# Start ZThumb local thumbnail engine
zthumb-up:
	cd zthumb && ./run_zthumb.sh

# Alias (per training/inference workflow docs)
run_zthumb: zthumb-up

# Stop ZThumb local thumbnail engine
zthumb-down:
	cd zthumb && (docker compose down || docker-compose down)

# One-button local smoke test (ZThumb + voice support + ffmpeg)
smoke:
	./scripts/smoke.sh

# Build training image (auto-select cpu/cuda) and train LoRA.
# Customize:
#   TIER=12gb STEPS=1500 LR=1e-4 RANK=16 OUTPUT=outputs/lora/zthumb_lora make train_lora
train_lora:
	@./scripts/train_lora.sh

# Evaluate LoRA (before/after grids + TRAINING_REPORT.md)
eval_lora:
	@./scripts/eval_lora.sh

# Call ZThumb API and copy 4 generated images into outputs/test_generate/
test_generate:
	@./scripts/test_generate.sh

# Import n8n workflows
import-workflows:
	@echo "Import workflows manually via n8n UI at http://localhost:5678"
	@echo "Workflow files are in n8n/workflows/"

# Export n8n workflows
export-workflows:
	@echo "Export workflows manually via n8n UI"
	@echo "Save to n8n/workflows/"

# Development mode with hot reload
dev:
	docker-compose -f docker-compose.yml -f docker-compose.dev.yml up

# Show help
help:
	@echo "Amharic Recap Autopilot - Available Commands"
	@echo ""
	@echo "  make up          - Start all services"
	@echo "  make down        - Stop all services"
	@echo "  make logs        - View all logs"
	@echo "  make build       - Build Docker images"
	@echo "  make rebuild     - Rebuild and start"
	@echo "  make clean       - Remove volumes and images"
	@echo "  make test        - Run tests"
	@echo "  make shell       - Shell into runner container"
	@echo "  make discover    - Run channel discovery"
	@echo "  make process VIDEO_ID=xxx - Process a video"
	@echo "  make report      - Generate daily report"
	@echo "  make health      - Check service health"
	@echo "  make help        - Show this help"
