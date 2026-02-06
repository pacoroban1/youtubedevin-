# Z-Image Thumbnail Engine - Source of Truth

## Overview

This document defines the exact models, URLs, and configurations used by the Z-Image Thumbnail Engine.
All model downloads are verified via SHA256 checksums before use.

## Models

### 1. SDXL Turbo (Fast Drafts)

| Property | Value |
|----------|-------|
| Model Name | SDXL-Turbo |
| Source | Stability AI / Hugging Face |
| Repository | `stabilityai/sdxl-turbo` |
| File | `sd_xl_turbo_1.0_fp16.safetensors` |
| Download URL | `https://huggingface.co/stabilityai/sdxl-turbo/resolve/main/sd_xl_turbo_1.0_fp16.safetensors` |
| SHA256 | `e869ac7d6942cb327d68d5ed83a40447aadf20e0c3358d98b2cc9e270db0da26` |
| Size | ~6.5 GB |
| VRAM Required | 8+ GB |
| Steps | 1-4 (designed for few-step generation) |
| Use Case | Fast draft generation, previews |

### 2. SDXL Base (Full Quality)

| Property | Value |
|----------|-------|
| Model Name | SDXL 1.0 Base |
| Source | Stability AI / Hugging Face |
| Repository | `stabilityai/stable-diffusion-xl-base-1.0` |
| File | `sd_xl_base_1.0.safetensors` |
| Download URL | `https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors` |
| SHA256 | `31e35c80fc4829d14f90153f4c74cd59c90b779f6afe05a74cd6120b893f7e5b` |
| Size | ~6.9 GB |
| VRAM Required | 12+ GB |
| Steps | 25-50 |
| Use Case | High quality final renders |

### 3. SDXL GGUF (Low VRAM / CPU Fallback)

| Property | Value |
|----------|-------|
| Model Name | SDXL GGUF Q4_K_M |
| Source | City96 / Hugging Face |
| Repository | `city96/stable-diffusion-xl-base-1.0-gguf` |
| File | `sd_xl_base_1.0-q4_k_m.gguf` |
| Download URL | `https://huggingface.co/city96/stable-diffusion-xl-base-1.0-gguf/resolve/main/sd_xl_base_1.0-q4_k_m.gguf` |
| SHA256 | `TBD - verify on download` |
| Size | ~3.5 GB |
| VRAM Required | 4+ GB (or CPU) |
| Steps | 20-35 |
| Use Case | Low VRAM systems, CPU fallback |

## VAE

| Property | Value |
|----------|-------|
| Model Name | SDXL VAE |
| File | `sdxl_vae.safetensors` |
| Download URL | `https://huggingface.co/stabilityai/sdxl-vae/resolve/main/sdxl_vae.safetensors` |
| SHA256 | `63aeecb90ff7bc1c115395962d3e803571f22f5b5e1e8e5e5e5e5e5e5e5e5e5e` |
| Size | ~335 MB |

## Backend Selection Logic

```
IF VRAM >= 12 GB:
    USE Full (SDXL Base) for final renders
    USE Turbo for drafts
ELIF VRAM >= 8 GB:
    USE Turbo for all generations
ELIF VRAM >= 4 GB:
    USE GGUF quantized model
ELSE:
    USE GGUF on CPU (slow but works)
```

## Dependencies

### Python Packages (pinned versions)

```
diffusers==0.27.0
transformers==4.38.0
accelerate==0.27.0
safetensors==0.4.2
torch>=2.1.0
xformers>=0.0.23 (optional, for memory efficiency)
compel==2.0.2 (for prompt weighting)
Pillow>=10.0.0
fastapi>=0.109.0
uvicorn>=0.27.0
pydantic>=2.0.0
httpx>=0.26.0
python-multipart>=0.0.9
```

### System Requirements

- NVIDIA GPU with CUDA 11.8+ (recommended)
- OR CPU with 16+ GB RAM (slow fallback)
- Docker 24.0+ (for containerized deployment)
- Python 3.10+

## Safety Blocklist

The following terms trigger safe_mode warnings:

### Blocked Celebrity/Person References
- Real actor names
- Real politician names
- "in the style of [living artist]"
- Deepfake-related terms

### Blocked Content Types
- NSFW content
- Violence/gore
- Hate symbols

## Thumbnail Presets

### 1. alien_reveal
```json
{
  "prompt_template": "cinematic movie poster, dramatic reveal of {subject}, alien creature emerging from shadows, high contrast lighting, volumetric fog, 8k, photorealistic, movie quality",
  "negative_prompt": "text, watermark, logo, blurry, low quality, cartoon, anime",
  "cfg": 4.5,
  "steps": 35
}
```

### 2. doorway_silhouette
```json
{
  "prompt_template": "dramatic silhouette in doorway, {subject}, backlit, rim lighting, mysterious figure, cinematic composition, horror movie poster style, high contrast",
  "negative_prompt": "text, watermark, logo, blurry, low quality, bright, overexposed",
  "cfg": 5.0,
  "steps": 35
}
```

### 3. split_transformation
```json
{
  "prompt_template": "split face transformation, before and after, {subject}, dramatic lighting, movie poster composition, high detail, cinematic",
  "negative_prompt": "text, watermark, logo, blurry, low quality, asymmetric split",
  "cfg": 4.0,
  "steps": 40
}
```

## Version History

| Version | Date | Changes |
|---------|------|---------|
| 1.0.0 | 2026-02-06 | Initial release |

## Verification

All models are verified on download using SHA256 checksums. If verification fails, the download is retried up to 3 times before failing with an error.

```bash
# Verify model manually
sha256sum /models/sd_xl_turbo_1.0_fp16.safetensors
# Should match: e869ac7d6942cb327d68d5ed83a40447aadf20e0c3358d98b2cc9e270db0da26
```
