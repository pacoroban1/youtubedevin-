# Z-Image Thumbnail Engine

Zero-setup local image generation system for YouTube thumbnails with auto VRAM detection and model selection.

## Features

- **Zero Setup**: One command to install and run
- **Auto VRAM Detection**: Automatically selects best model based on your GPU
- **Multiple Backends**: Full (12GB+), Turbo (8GB+), GGUF (4GB+/CPU)
- **Safety Filter**: Blocks unsafe prompts by default
- **Style Presets**: Pre-configured styles for YouTube thumbnails
- **Two-Pass Strategy**: Fast drafts + quality finals
- **REST API**: Simple HTTP API for integration

## Quick Start

```bash
# One command to start
./run_zthumb.sh

# Or with Docker Compose directly
docker compose up -d
```

## API Endpoints

### Health Check
```bash
curl http://localhost:8100/health
```

Response:
```json
{
  "status": "ok",
  "backend": "turbo",
  "vram_mb": 8192,
  "gpu": true,
  "cuda_available": true,
  "models_available": ["sdxl-turbo"]
}
```

### List Models
```bash
curl http://localhost:8100/models
```

### Generate Thumbnails
```bash
curl -X POST http://localhost:8100/generate \
  -H "Content-Type: application/json" \
  -d '{
    "prompt": "cinematic alien creature reveal, dramatic lighting",
    "batch": 4,
    "style_preset": "alien_reveal"
  }'
```

Request Schema:
```json
{
  "prompt": "...",
  "negative_prompt": "...",
  "width": 1280,
  "height": 720,
  "seed": 12345,
  "steps": 35,
  "cfg": 4.0,
  "sampler": "euler",
  "variant": "auto|turbo|full|gguf",
  "batch": 4,
  "output_format": "png",
  "upscale": true,
  "face_detail": true,
  "safe_mode": true,
  "style_preset": "alien_reveal|doorway_silhouette|split_transformation",
  "subject": "mysterious creature"
}
```

## Style Presets

### alien_reveal
High contrast alien creature reveal with dramatic lighting and volumetric fog.

### doorway_silhouette
Dramatic silhouette in doorway with backlit rim lighting, horror movie poster style.

### split_transformation
Split face transformation effect, before/after with dramatic lighting.

## Python Client

```python
from zthumb_client import ZThumbClient, generate_thumbnail, two_pass_generate

# Simple usage
with ZThumbClient() as client:
    result = client.generate(
        prompt="cinematic alien reveal",
        batch=4
    )
    print(result["images"])

# Convenience function
images = generate_thumbnail({
    "prompt": "mysterious creature in shadows",
    "style_preset": "doorway_silhouette"
})

# Two-pass strategy (drafts + quality)
result = two_pass_generate(
    prompt="epic transformation scene",
    subject="werewolf",
    style_preset="split_transformation"
)
```

## CLI Usage

```bash
# Check health
python zthumb_client.py health

# List models
python zthumb_client.py models

# Generate thumbnails
python zthumb_client.py generate "cinematic alien reveal" --batch 4

# Use preset
python zthumb_client.py generate "mysterious figure" --preset doorway_silhouette

# Two-pass generation
python zthumb_client.py two-pass "epic transformation" --subject "werewolf"
```

## VRAM Requirements

| Backend | VRAM Required | Quality | Speed |
|---------|---------------|---------|-------|
| Full    | 12+ GB        | Best    | Slow  |
| Turbo   | 8+ GB         | Good    | Fast  |
| GGUF    | 4+ GB / CPU   | Good    | Medium|

## Directory Structure

```
/zthumb
  /server          # FastAPI application
  /backends        # Backend implementations (full/turbo/gguf/auto)
  /scripts         # Utility scripts (detect, download, verify)
  /docs            # Documentation
  /outputs         # Generated images (mounted volume)
  /models          # Model files (mounted volume)
  docker-compose.yml
  run_zthumb.sh    # One-command installer
  zthumb_client.py # Python client & CLI
```

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| ZTHUMB_MODELS_DIR | /models | Directory for model files |
| ZTHUMB_OUTPUTS_DIR | /outputs | Directory for generated images |
| ZTHUMB_SAFE_MODE | true | Enable safety filter |

## Safety Features

The engine includes a safety filter that blocks:
- Real celebrity/actor names
- "In the style of [living artist]"
- NSFW content
- Violence/gore

To disable (not recommended):
```bash
curl -X POST http://localhost:8100/generate \
  -d '{"prompt": "...", "safe_mode": false}'
```

## Troubleshooting

### No GPU detected
The engine will fall back to GGUF/CPU mode. Generation will be slower but still work.

### Out of memory
Try:
1. Reduce batch size
2. Use `variant: "gguf"` explicitly
3. Reduce resolution

### Models not downloading
Check your internet connection and disk space. Models are ~3-7GB each.

## Integration with Amharic Recap Autopilot

This engine integrates with the main pipeline via the thumbnail module:

```python
# In services/runner/modules/thumbnail.py
from zthumb_client import generate_thumbnail

async def generate_thumbnails(video_id: str, concepts: list):
    thumbnails = []
    for concept in concepts:
        result = generate_thumbnail(concept)
        thumbnails.extend(result)
    return thumbnails
```
