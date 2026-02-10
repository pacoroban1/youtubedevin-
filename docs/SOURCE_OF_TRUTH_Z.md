# SOURCE OF TRUTH: “Z” (ZThumb Model + Inference Path + LoRA Injection)

This document is evidence-based from the repo contents in `zthumb/` as of 2026-02-06.

## What “Z” Actually Is

ZThumb is a **Diffusers (Hugging Face) SDXL** inference server (FastAPI) with multiple backends:

- **Turbo backend**: `stabilityai/sdxl-turbo`
  - Loaded via Diffusers `AutoPipelineForText2Image`
  - Code: `zthumb/backends/turbo.py`
- **Full backend**: `stabilityai/stable-diffusion-xl-base-1.0`
  - Loaded via Diffusers `StableDiffusionXLPipeline`
  - Code: `zthumb/backends/full.py`
- **GGUF backend (low VRAM/CPU)**: currently *still uses* `stabilityai/stable-diffusion-xl-base-1.0`
  - Code: `zthumb/backends/gguf.py`
  - Note: the “GGUF” file is tracked in `zthumb/docs/SOURCE_OF_TRUTH.md`, but the actual loader currently falls back to regular SDXL pipeline.

Models and download URLs are documented in `zthumb/docs/SOURCE_OF_TRUTH.md`.

## Inference Code Path Used By ZThumb

Request flow for image generation:

1. HTTP `POST /generate` → `zthumb/server/main.py`
2. Backend selection:
   - `select_backend(...)` in `zthumb/server/main.py`
3. Backend instantiation:
   - `from backends import get_backend` → `zthumb/backends/__init__.py`
4. Generation:
   - `backend_instance.generate(...)` → one of:
     - `zthumb/backends/turbo.py:TurboBackend.generate`
     - `zthumb/backends/full.py:FullBackend.generate`
     - `zthumb/backends/gguf.py:GGUFBackend.generate`

The actual Diffusers pipeline is created lazily inside each backend’s `_load_pipeline()` method.

## Where LoRA Is Injected

LoRA adapter loading happens in:

- `zthumb/backends/base.py:BaseBackend.apply_lora(...)`

It is applied right before generation (per request) in:

- `zthumb/backends/turbo.py` (`_generate_sync`)
- `zthumb/backends/full.py` (`_generate_sync`)
- `zthumb/backends/gguf.py` (`_generate_sync`)

## LoRA Runtime Controls (Inference)

Environment variables (preferred names per project spec):

- `Z_LORA_PATH=/outputs/lora/<adapter_dir_or_file>`
- `Z_LORA_SCALE=0.8`

Backward-compatible aliases supported:

- `ZTHUMB_LORA_PATH`
- `ZTHUMB_LORA_SCALE`

API control:

- `POST /generate` accepts optional `lora_scale` to override the env scale for that request.

Model listing:

- `GET /models` includes `lora_loaded` + `lora_path` based on whether the adapter path exists inside the container.

