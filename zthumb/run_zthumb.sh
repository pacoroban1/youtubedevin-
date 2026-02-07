#!/bin/bash
#
# Z-Image Thumbnail Engine - One Command Setup & Run
# Usage: ./run_zthumb.sh
#
# This script:
# 1) Detects GPU + VRAM
# 2) Downloads appropriate models
# 3) Starts the server via Docker Compose
#

set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"
BASE_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${BLUE}║       Z-Image Thumbnail Engine - Zero Setup Installer      ║${NC}"
echo -e "${BLUE}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""

# Check for Docker
if ! command -v docker &> /dev/null; then
    echo -e "${RED}Error: Docker is not installed.${NC}"
    echo "Please install Docker: https://docs.docker.com/get-docker/"
    exit 1
fi

if ! command -v docker-compose &> /dev/null && ! docker compose version &> /dev/null; then
    echo -e "${RED}Error: Docker Compose is not installed.${NC}"
    echo "Please install Docker Compose: https://docs.docker.com/compose/install/"
    exit 1
fi

# Detect GPU
echo -e "${YELLOW}[1/4] Detecting GPU...${NC}"
VRAM_MB=0
GPU_NAME="None"

if command -v nvidia-smi &> /dev/null; then
    GPU_INFO=$(nvidia-smi --query-gpu=name,memory.total --format=csv,noheader,nounits 2>/dev/null || echo "")
    if [ -n "$GPU_INFO" ]; then
        GPU_NAME=$(echo "$GPU_INFO" | cut -d',' -f1 | xargs)
        VRAM_MB=$(echo "$GPU_INFO" | cut -d',' -f2 | xargs)
        echo -e "${GREEN}  GPU Found: $GPU_NAME${NC}"
        echo -e "${GREEN}  VRAM: ${VRAM_MB} MB${NC}"
    fi
else
    echo -e "${YELLOW}  No NVIDIA GPU detected (nvidia-smi not found)${NC}"
fi

# Determine backend
echo ""
echo -e "${YELLOW}[2/4] Selecting optimal backend...${NC}"
if [ "$VRAM_MB" -ge 12000 ]; then
    BACKEND="full"
    echo -e "${GREEN}  Selected: FULL (High Quality) - VRAM >= 12GB${NC}"
elif [ "$VRAM_MB" -ge 8000 ]; then
    BACKEND="turbo"
    echo -e "${GREEN}  Selected: TURBO (Fast Drafts) - VRAM >= 8GB${NC}"
elif [ "$VRAM_MB" -ge 4000 ]; then
    BACKEND="gguf"
    echo -e "${GREEN}  Selected: GGUF (Low VRAM) - VRAM >= 4GB${NC}"
else
    BACKEND="gguf"
    echo -e "${YELLOW}  Selected: GGUF (CPU Fallback) - Low/No GPU${NC}"
fi

# Default envs for Docker Compose (can be overridden by user env or zthumb/.env).
if [ -z "${ZTHUMB_ALLOW_REMOTE_DOWNLOAD:-}" ]; then
    if [ "$VRAM_MB" -ge 8000 ]; then
        ZTHUMB_ALLOW_REMOTE_DOWNLOAD="true"
    else
        ZTHUMB_ALLOW_REMOTE_DOWNLOAD="false"
    fi
fi

if [ -z "${ZTHUMB_TURBO_MODEL_ID:-}" ]; then
    if [ "$VRAM_MB" -ge 8000 ]; then
        ZTHUMB_TURBO_MODEL_ID="stabilityai/sdxl-turbo"
    else
        ZTHUMB_TURBO_MODEL_ID="stabilityai/sd-turbo"
    fi
fi

# Create directories
echo ""
echo -e "${YELLOW}[3/4] Setting up directories...${NC}"
mkdir -p "$BASE_DIR/models" "$BASE_DIR/outputs"
echo -e "${GREEN}  Created: $BASE_DIR/models/, $BASE_DIR/outputs/${NC}"

# Optional: download models on the host so the container sees them under /models.
if [ "${ZTHUMB_AUTO_DOWNLOAD_MODELS:-false}" = "true" ]; then
    echo -e "${YELLOW}  Downloading recommended models (ZTHUMB_AUTO_DOWNLOAD_MODELS=true)...${NC}"
    python3 scripts/download_models.py --variant auto --models-dir "$BASE_DIR/models" --vram "$VRAM_MB"
else
    echo -e "${YELLOW}  Skipping model download. To download: ZTHUMB_AUTO_DOWNLOAD_MODELS=true ./run_zthumb.sh${NC}"
fi

# Create .env if not exists
if [ ! -f .env ]; then
    cp .env.example .env 2>/dev/null || cat > .env << EOF
# Z-Image Thumbnail Engine Configuration
ZTHUMB_MODELS_DIR=/models
ZTHUMB_OUTPUTS_DIR=/outputs
ZTHUMB_SAFE_MODE=true
ZTHUMB_DEFAULT_BACKEND=$BACKEND
EOF
    echo -e "${GREEN}  Created: .env${NC}"
fi

# Start services
echo ""
echo -e "${YELLOW}[4/4] Starting Z-Image Thumbnail Engine...${NC}"

# Use docker compose (v2) or docker-compose (v1)
if docker compose version &> /dev/null; then
    COMPOSE_CMD="docker compose"
else
    COMPOSE_CMD="docker-compose"
fi

ZTHUMB_DEFAULT_BACKEND="$BACKEND" \
ZTHUMB_ALLOW_REMOTE_DOWNLOAD="$ZTHUMB_ALLOW_REMOTE_DOWNLOAD" \
ZTHUMB_TURBO_MODEL_ID="$ZTHUMB_TURBO_MODEL_ID" \
$COMPOSE_CMD up -d --build

echo ""
echo -e "${GREEN}╔════════════════════════════════════════════════════════════╗${NC}"
echo -e "${GREEN}║              Z-Image Thumbnail Engine Started!             ║${NC}"
echo -e "${GREEN}╚════════════════════════════════════════════════════════════╝${NC}"
echo ""
echo -e "  ${BLUE}API Server:${NC}    http://localhost:8100"
echo -e "  ${BLUE}Health Check:${NC}  curl http://localhost:8100/health"
echo -e "  ${BLUE}Models:${NC}        curl http://localhost:8100/models"
echo ""
echo -e "  ${YELLOW}Example generation:${NC}"
echo '  curl -X POST http://localhost:8100/generate \'
echo '    -H "Content-Type: application/json" \'
echo '    -d '"'"'{"prompt": "cinematic alien creature reveal, dramatic lighting", "batch": 4}'"'"
echo ""
echo -e "  ${YELLOW}To stop:${NC} $COMPOSE_CMD down"
echo ""

# Wait for health check
echo -e "${YELLOW}Waiting for server to be ready...${NC}"
for i in {1..30}; do
    if curl -s http://localhost:8100/health > /dev/null 2>&1; then
        echo -e "${GREEN}Server is ready!${NC}"
        curl -s http://localhost:8100/health | python3 -m json.tool 2>/dev/null || curl -s http://localhost:8100/health
        exit 0
    fi
    sleep 1
done

echo -e "${YELLOW}Server is starting... Check logs with: $COMPOSE_CMD logs -f${NC}"
