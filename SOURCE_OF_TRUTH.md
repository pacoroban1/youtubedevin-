# SOURCE OF TRUTH (Training + Inference for “Z” LoRA)

This file is intentionally **evidence-first**: every claim maps to a file in this repo.

If you change any versions/URLs/SHA256 values, update this file in the same commit.

## Base Model (Training)

LoRA training in this repo targets **SDXL Base 1.0** (full-quality backend).

- **Model repo**: `stabilityai/stable-diffusion-xl-base-1.0`
- **Local filename (repo convention)**: `models/sd_xl_base_1.0.safetensors`
- **Download URL**: `https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors`
- **SHA256**: `31e35c80fc4829d14f90153f4c74cd59c90b779f6afe05a74cd6120b893f7e5b`

Source of truth:
- `zthumb/scripts/download_models.py` (download URL + SHA256)
- `zthumb/docs/SOURCE_OF_TRUTH.md` (human-readable table)

Notes:
- These StabilityAI weights may be gated on Hugging Face. If downloads fail, set an HF token in the environment used for downloading (commonly `HF_TOKEN` / `HUGGINGFACE_HUB_TOKEN`) and ensure you accepted the model license.

## Trainer Implementation

The LoRA trainer is implemented in pure Python using **Diffusers attention-processor LoRA**:

- Trainer entrypoint: `training/train_lora.py`
  - SDXL pipeline: `StableDiffusionXLPipeline`
  - LoRA injection: `LoRAAttnProcessor2_0` + `AttnProcsLayers`
  - Output format: Diffusers-compatible directory for `pipe.load_lora_weights(<dir>)`

Dataset builder:
- `training/prepare_dataset.py`
- `datasets/README.md` (dataset layout + caption format)

Evaluation (end-to-end through the ZThumb API):
- `scripts/eval_lora_report.py`
  - Calls `POST /generate` with `lora_scale=0` vs `lora_scale=0.8` using the same seed(s)
  - Writes `outputs/lora_eval/<run>/report.md` + side-by-side images

## Pinned Versions (Training)

The “push-button” pipeline runs training inside a Docker image (GPU):
- Dockerfile: `training/Dockerfile.cuda`
- Base image: `pytorch/pytorch:2.2.2-cuda12.1-cudnn8-runtime`
- Python deps: `training/requirements.base.txt`

Pinned deps (see `training/requirements.base.txt`):
- `diffusers==0.27.0`
- `transformers==4.38.0`
- `accelerate==0.27.0`
- `safetensors==0.4.2`
- `compel==2.0.2`
- `peft==0.10.0`

CPU-only training image (for completeness, not used by `make finetune_z`):
- Dockerfile: `training/Dockerfile.cpu`
- Python deps: `training/requirements.cpu.txt` (pins `torch==2.2.2`, `torchvision==0.17.2`)

## Inference Implementation (ZThumb)

ZThumb is a FastAPI inference server with multiple SDXL backends.

- API server: `zthumb/server/main.py`
- Backends:
  - Turbo: `zthumb/backends/turbo.py`
  - Full (SDXL base): `zthumb/backends/full.py`
  - GGUF fallback: `zthumb/backends/gguf.py` (currently still loads SDXL base pipeline)
- LoRA injection point:
  - `zthumb/backends/base.py:BaseBackend.apply_lora(...)`

Inference runtime controls (backward compatible):
- Env:
  - `Z_LORA_PATH` / `Z_LORA_SCALE`
  - Aliases: `ZTHUMB_LORA_PATH` / `ZTHUMB_LORA_SCALE`
- API:
  - `POST /generate`: accepts optional `lora_path` + `lora_scale` overrides per request
  - `GET /models`: includes `lora_loaded` + `lora_path` for env-default LoRA

## Push-Button Entry Point

Single-command GPU pipeline (dataset → train → export → API eval report):
- `make finetune_z`
- Implementation: `scripts/finetune_z.sh`

Output conventions:
- Training logs + checkpoints: `outputs/lora/<run_name>/`
- Exported adapter for inference: `models/lora/<run_name>/`
- API-based eval report: `outputs/lora_eval/<run_name>/report.md`

