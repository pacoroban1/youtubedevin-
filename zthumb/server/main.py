"""
Z-Image Thumbnail Engine - FastAPI Server
Zero-setup local image generation with auto VRAM detection and model selection.
"""

import os
import json
import hashlib
import subprocess
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Literal
from enum import Enum

from fastapi import FastAPI, HTTPException, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

app = FastAPI(
    title="Z-Image Thumbnail Engine",
    description="Zero-setup local image generation with auto VRAM detection",
    version="1.0.0"
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Configuration
MODELS_DIR = os.getenv("ZTHUMB_MODELS_DIR", "/models")
OUTPUTS_DIR = os.getenv("ZTHUMB_OUTPUTS_DIR", "/outputs")
SAFE_MODE_DEFAULT = os.getenv("ZTHUMB_SAFE_MODE", "true").lower() == "true"


class VariantType(str, Enum):
    AUTO = "auto"
    TURBO = "turbo"
    FULL = "full"
    GGUF = "gguf"


class StylePreset(str, Enum):
    ALIEN_REVEAL = "alien_reveal"
    DOORWAY_SILHOUETTE = "doorway_silhouette"
    SPLIT_TRANSFORMATION = "split_transformation"
    CUSTOM = "custom"


class GenerateRequest(BaseModel):
    prompt: str = Field(..., description="Main prompt for image generation")
    negative_prompt: str = Field(
        default="text, watermark, logo, blurry, low quality, cartoon, anime, deformed hands",
        description="Negative prompt to avoid unwanted elements"
    )
    width: int = Field(default=1280, ge=512, le=2048)
    height: int = Field(default=720, ge=512, le=2048)
    seed: Optional[int] = Field(default=None, description="Random seed for reproducibility")
    steps: int = Field(default=35, ge=1, le=100)
    cfg: float = Field(default=4.0, ge=1.0, le=20.0)
    sampler: str = Field(default="euler", description="Sampling method")
    variant: VariantType = Field(default=VariantType.AUTO)
    batch: int = Field(default=4, ge=1, le=8)
    output_format: Literal["png", "jpg", "webp"] = Field(default="png")
    upscale: bool = Field(default=True, description="Apply 2x upscale + sharpen")
    face_detail: bool = Field(default=True, description="Apply face detail pass")
    safe_mode: bool = Field(default=True, description="Block unsafe prompts")
    style_preset: Optional[StylePreset] = Field(default=None)
    subject: Optional[str] = Field(default=None, description="Subject for preset templates")
    lora_scale: Optional[float] = Field(default=None, ge=0.0, le=2.0, description="Optional per-request LoRA scale override")


class GenerateResponse(BaseModel):
    images: List[str]
    meta: dict
    warnings: List[str] = []


class HealthResponse(BaseModel):
    status: str
    backend: str
    vram_mb: int
    gpu: bool
    cuda_available: bool
    models_available: List[str]


class ModelsResponse(BaseModel):
    models: List[dict]
    recommended: str
    vram_mb: int
    lora_loaded: bool = False
    lora_path: Optional[str] = None


# Safety blocklist
BLOCKED_TERMS = [
    # Celebrities/actors (examples)
    "holt mccallany", "brad pitt", "tom cruise", "scarlett johansson",
    "taylor swift", "elon musk", "donald trump", "joe biden",
    # Unsafe content
    "nsfw", "nude", "naked", "porn", "xxx", "gore", "violence",
    "in the style of", "deepfake",
]

# Preset templates
PRESETS = {
    StylePreset.ALIEN_REVEAL: {
        "prompt_template": "cinematic movie poster, dramatic reveal of {subject}, alien creature emerging from shadows, high contrast lighting, volumetric fog, 8k, photorealistic, movie quality",
        "negative_prompt": "text, watermark, logo, blurry, low quality, cartoon, anime",
        "cfg": 4.5,
        "steps": 35
    },
    StylePreset.DOORWAY_SILHOUETTE: {
        "prompt_template": "dramatic silhouette in doorway, {subject}, backlit, rim lighting, mysterious figure, cinematic composition, horror movie poster style, high contrast",
        "negative_prompt": "text, watermark, logo, blurry, low quality, bright, overexposed",
        "cfg": 5.0,
        "steps": 35
    },
    StylePreset.SPLIT_TRANSFORMATION: {
        "prompt_template": "split face transformation, before and after, {subject}, dramatic lighting, movie poster composition, high detail, cinematic",
        "negative_prompt": "text, watermark, logo, blurry, low quality, asymmetric split",
        "cfg": 4.0,
        "steps": 40
    }
}


def get_gpu_info() -> dict:
    """Detect GPU and VRAM information."""
    info = {
        "gpu": False,
        "cuda_available": False,
        "vram_mb": 0,
        "gpu_name": "None"
    }
    
    try:
        # Try nvidia-smi first
        result = subprocess.run(
            ["nvidia-smi", "--query-gpu=name,memory.total", "--format=csv,noheader,nounits"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            lines = result.stdout.strip().split("\n")
            if lines and lines[0]:
                parts = lines[0].split(", ")
                info["gpu"] = True
                info["gpu_name"] = parts[0] if len(parts) > 0 else "Unknown"
                info["vram_mb"] = int(parts[1]) if len(parts) > 1 else 0
    except Exception:
        pass
    
    # Check CUDA availability via torch
    try:
        import torch
        info["cuda_available"] = torch.cuda.is_available()
        if info["cuda_available"] and not info["gpu"]:
            info["gpu"] = True
            info["vram_mb"] = torch.cuda.get_device_properties(0).total_memory // (1024 * 1024)
            info["gpu_name"] = torch.cuda.get_device_name(0)
    except ImportError:
        pass
    
    return info


def get_available_models() -> List[dict]:
    """Get list of available models."""
    models = []
    models_path = Path(MODELS_DIR)
    
    model_configs = [
        {
            "name": "sdxl-turbo",
            "file": "sd_xl_turbo_1.0_fp16.safetensors",
            "variant": "turbo",
            "vram_required": 8000,
            "description": "Fast drafts (1-4 steps)"
        },
        {
            "name": "sdxl-base",
            "file": "sd_xl_base_1.0.safetensors",
            "variant": "full",
            "vram_required": 12000,
            "description": "High quality (25-50 steps)"
        },
        {
            "name": "sdxl-gguf",
            "file": "sd_xl_base_1.0-q4_k_m.gguf",
            "variant": "gguf",
            "vram_required": 4000,
            "description": "Low VRAM / CPU fallback"
        }
    ]
    
    for config in model_configs:
        model_path = models_path / config["file"]
        config["available"] = model_path.exists()
        config["path"] = str(model_path) if config["available"] else None
        models.append(config)
    
    return models


def select_backend(vram_mb: int, requested_variant: VariantType, available_models: List[dict]) -> str:
    """Select best backend based on VRAM and availability."""
    available_variants = {m["variant"] for m in available_models if m["available"]}
    allow_remote = os.getenv("ZTHUMB_ALLOW_REMOTE_DOWNLOAD", "false").strip().lower() in ("1", "true", "yes", "on")
    
    # If the caller explicitly requests a variant, honor it even if the model
    # isn't present locally. Backends can fall back to downloading from HF.
    if requested_variant != VariantType.AUTO:
        return requested_variant.value
    
    # Prefer locally available variants when present.
    if vram_mb >= 12000 and "full" in available_variants:
        return "full"
    if vram_mb >= 8000 and "turbo" in available_variants:
        return "turbo"
    if "gguf" in available_variants:
        return "gguf"
    if "turbo" in available_variants:
        return "turbo"

    # No local models found.
    # By default we *do not* auto-download multi-GB models. Enable explicitly.
    if not allow_remote:
        return "placeholder"

    # If remote downloads are allowed, choose a reasonable default based on VRAM
    # and let the backend download the base model from HuggingFace on first run.
    if vram_mb >= 12000:
        return "full"
    if vram_mb >= 8000:
        return "turbo"
    # On CPU (common on Mac dev machines), prefer the smaller Turbo model to
    # avoid multi-GB SDXL base downloads.
    if vram_mb == 0:
        return "turbo"
    return "gguf"


def check_safety(prompt: str, negative_prompt: str) -> List[str]:
    """Check prompt for blocked terms."""
    warnings = []
    combined = (prompt + " " + negative_prompt).lower()
    
    for term in BLOCKED_TERMS:
        if term in combined:
            warnings.append(f"Blocked term detected: '{term}'. Safe mode enabled.")
    
    return warnings


def apply_preset(request: GenerateRequest) -> GenerateRequest:
    """Apply style preset to request."""
    if request.style_preset and request.style_preset != StylePreset.CUSTOM:
        preset = PRESETS.get(request.style_preset)
        if preset:
            subject = request.subject or "mysterious creature"
            request.prompt = preset["prompt_template"].format(subject=subject)
            request.negative_prompt = preset["negative_prompt"]
            request.cfg = preset["cfg"]
            request.steps = preset["steps"]
    return request


def get_lora_status() -> dict:
    lora_path = os.getenv("Z_LORA_PATH") or os.getenv("ZTHUMB_LORA_PATH")
    exists = False
    if lora_path:
        try:
            exists = Path(lora_path).exists()
        except Exception:
            exists = False
    return {"lora_loaded": bool(lora_path and exists), "lora_path": lora_path}


@app.get("/health", response_model=HealthResponse)
async def health():
    """Health check with GPU/VRAM info."""
    gpu_info = get_gpu_info()
    models = get_available_models()
    backend = select_backend(gpu_info["vram_mb"], VariantType.AUTO, models)
    
    return HealthResponse(
        status="ok",
        backend=backend,
        vram_mb=gpu_info["vram_mb"],
        gpu=gpu_info["gpu"],
        cuda_available=gpu_info["cuda_available"],
        models_available=[m["name"] for m in models if m["available"]]
    )


@app.get("/models", response_model=ModelsResponse)
async def list_models():
    """List available models and variants."""
    gpu_info = get_gpu_info()
    models = get_available_models()
    recommended = select_backend(gpu_info["vram_mb"], VariantType.AUTO, models)
    lora = get_lora_status()
    
    return ModelsResponse(
        models=models,
        recommended=recommended,
        vram_mb=gpu_info["vram_mb"],
        lora_loaded=lora["lora_loaded"],
        lora_path=lora["lora_path"]
    )


@app.post("/generate", response_model=GenerateResponse)
async def generate(request: GenerateRequest, background_tasks: BackgroundTasks):
    """Generate thumbnail images."""
    import time
    start_time = time.time()
    
    # Apply preset if specified
    request = apply_preset(request)
    
    # Safety check
    warnings = []
    if request.safe_mode:
        warnings = check_safety(request.prompt, request.negative_prompt)
        if warnings:
            # Return placeholder response with warnings
            return GenerateResponse(
                images=[],
                meta={
                    "seed": request.seed or 0,
                    "backend": "blocked",
                    "variant_used": "none",
                    "timings": {"total": 0},
                    "blocked": True
                },
                warnings=warnings
            )
    
    # Get GPU info and select backend
    gpu_info = get_gpu_info()
    models = get_available_models()
    backend = select_backend(gpu_info["vram_mb"], request.variant, models)
    
    # Create output directory
    today = datetime.now().strftime("%Y-%m-%d")
    job_id = hashlib.md5(f"{request.prompt}{time.time()}".encode()).hexdigest()[:12]
    output_dir = Path(OUTPUTS_DIR) / today / job_id
    output_dir.mkdir(parents=True, exist_ok=True)
    
    # Generate images using selected backend
    images = []
    seed = request.seed or int(time.time()) % 2**32
    
    try:
        if backend == "placeholder":
            # No models available - return placeholder
            warnings.append("No models available. Please run the installer to download models.")
            # Create placeholder images
            from PIL import Image, ImageDraw, ImageFont
            for i in range(request.batch):
                img = Image.new("RGB", (request.width, request.height), color=(40, 40, 40))
                draw = ImageDraw.Draw(img)
                text = f"Placeholder #{i+1}\nModels not installed"
                draw.text((request.width//2, request.height//2), text, fill=(200, 200, 200), anchor="mm")
                img_path = output_dir / f"img_{i+1}.{request.output_format}"
                img.save(img_path)
                images.append(f"file://{img_path}")
        else:
            # Import and use the appropriate backend
            from backends import get_backend
            backend_instance = get_backend(backend, models)
            
            generated = await backend_instance.generate(
                prompt=request.prompt,
                negative_prompt=request.negative_prompt,
                width=request.width,
                height=request.height,
                seed=seed,
                steps=request.steps,
                cfg=request.cfg,
                batch=request.batch,
                output_dir=output_dir,
                output_format=request.output_format,
                upscale=request.upscale,
                face_detail=request.face_detail,
                lora_scale=request.lora_scale
            )
            images = generated
            
    except ImportError as e:
        warnings.append(f"Backend import error: {e}. Using placeholder.")
        # Create placeholder
        from PIL import Image, ImageDraw
        for i in range(request.batch):
            img = Image.new("RGB", (request.width, request.height), color=(40, 40, 40))
            draw = ImageDraw.Draw(img)
            draw.text((request.width//2, request.height//2), f"Backend Error\n{str(e)[:50]}", fill=(200, 200, 200), anchor="mm")
            img_path = output_dir / f"img_{i+1}.{request.output_format}"
            img.save(img_path)
            images.append(f"file://{img_path}")
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    
    # Save metadata
    meta = {
        "seed": seed,
        "backend": backend,
        "variant_used": backend,
        "prompt": request.prompt,
        "negative_prompt": request.negative_prompt,
        "width": request.width,
        "height": request.height,
        "steps": request.steps,
        "cfg": request.cfg,
        "batch": request.batch,
        "timings": {
            "total": time.time() - start_time
        },
        "gpu_info": gpu_info
    }
    
    with open(output_dir / "meta.json", "w") as f:
        json.dump(meta, f, indent=2)
    
    return GenerateResponse(
        images=images,
        meta=meta,
        warnings=warnings
    )


if __name__ == "__main__":
    import uvicorn
    uvicorn.run(app, host="0.0.0.0", port=8100)
