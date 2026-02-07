#!/usr/bin/env python3
"""
Model Download Script
Downloads and verifies models for Z-Image Thumbnail Engine.
"""

import os
import sys
import hashlib
import urllib.request
from pathlib import Path
from typing import Optional


# Model configurations
MODELS = {
    "turbo": {
        "name": "SDXL-Turbo",
        "file": "sd_xl_turbo_1.0_fp16.safetensors",
        "url": "https://huggingface.co/stabilityai/sdxl-turbo/resolve/main/sd_xl_turbo_1.0_fp16.safetensors",
        "sha256": "e869ac7d6942cb327d68d5ed83a40447aadf20e0c3358d98b2cc9e270db0da26",
        "size_gb": 6.5,
        "vram_required": 8000
    },
    "full": {
        "name": "SDXL Base 1.0",
        "file": "sd_xl_base_1.0.safetensors",
        "url": "https://huggingface.co/stabilityai/stable-diffusion-xl-base-1.0/resolve/main/sd_xl_base_1.0.safetensors",
        "sha256": "31e35c80fc4829d14f90153f4c74cd59c90b779f6afe05a74cd6120b893f7e5b",
        "size_gb": 6.9,
        "vram_required": 12000
    },
    "gguf": {
        "name": "SDXL GGUF Q4_K_M",
        "file": "sd_xl_base_1.0-q4_k_m.gguf",
        "url": "https://huggingface.co/city96/stable-diffusion-xl-base-1.0-gguf/resolve/main/sd_xl_base_1.0-q4_k_m.gguf",
        "sha256": None,  # Will verify on first download
        "size_gb": 3.5,
        "vram_required": 4000
    }
}


def get_models_dir() -> Path:
    """Get the models directory."""
    return Path(os.getenv("ZTHUMB_MODELS_DIR", "/models"))


def verify_checksum(file_path: Path, expected_sha256: Optional[str]) -> bool:
    """Verify file checksum."""
    if expected_sha256 is None:
        return True  # Skip verification if no checksum provided
    
    sha256_hash = hashlib.sha256()
    with open(file_path, "rb") as f:
        for chunk in iter(lambda: f.read(8192), b""):
            sha256_hash.update(chunk)
    
    actual = sha256_hash.hexdigest()
    return actual == expected_sha256


def download_with_progress(url: str, dest: Path, expected_size_gb: float):
    """Download file with progress indicator."""
    print(f"Downloading to {dest}...")
    print(f"Expected size: ~{expected_size_gb} GB")

    # Some HF assets are gated. If a token is present, pass it as a bearer token.
    token = (
        os.getenv("HF_TOKEN")
        or os.getenv("HUGGINGFACE_HUB_TOKEN")
        or os.getenv("HUGGINGFACE_TOKEN")
    )
    headers = {}
    if token:
        headers["Authorization"] = f"Bearer {token}"

    tmp = dest.with_suffix(dest.suffix + ".part")
    try:
        req = urllib.request.Request(url, headers=headers)
        with urllib.request.urlopen(req) as resp, open(tmp, "wb") as f:
            total = resp.headers.get("Content-Length")
            total_size = int(total) if total and total.isdigit() else None

            downloaded = 0
            block_size = 1024 * 1024  # 1MB
            while True:
                chunk = resp.read(block_size)
                if not chunk:
                    break
                f.write(chunk)
                downloaded += len(chunk)

                if total_size:
                    percent = min(100, int(downloaded * 100 / total_size))
                    downloaded_mb = downloaded / (1024 * 1024)
                    total_mb = total_size / (1024 * 1024)
                    sys.stdout.write(f"\r  Progress: {percent}% ({downloaded_mb:.1f}/{total_mb:.1f} MB)")
                else:
                    downloaded_mb = downloaded / (1024 * 1024)
                    sys.stdout.write(f"\r  Downloaded: {downloaded_mb:.1f} MB")
                sys.stdout.flush()

        print()  # New line after progress
        tmp.replace(dest)
        return True
    except Exception as e:
        try:
            if tmp.exists():
                tmp.unlink()
        except Exception:
            pass
        print(f"\nDownload failed: {e}")
        if not token and "huggingface.co" in url:
            print("Hint: if this model is gated on Hugging Face, set HF_TOKEN and retry.")
        return False


def download_model(variant: str, models_dir: Path, force: bool = False) -> bool:
    """Download a specific model variant."""
    if variant not in MODELS:
        print(f"Unknown variant: {variant}")
        return False
    
    config = MODELS[variant]
    dest = models_dir / config["file"]
    
    # Check if already exists
    if dest.exists() and not force:
        print(f"Model {config['name']} already exists at {dest}")
        if config["sha256"]:
            print("Verifying checksum...")
            if verify_checksum(dest, config["sha256"]):
                print("Checksum verified!")
                return True
            else:
                print("Checksum mismatch! Re-downloading...")
        else:
            return True
    
    # Create directory if needed
    models_dir.mkdir(parents=True, exist_ok=True)
    
    # Download
    print(f"\nDownloading {config['name']}...")
    print(f"URL: {config['url']}")
    
    success = download_with_progress(config["url"], dest, config["size_gb"])
    
    if success and config["sha256"]:
        print("Verifying checksum...")
        if verify_checksum(dest, config["sha256"]):
            print("Checksum verified!")
        else:
            print("WARNING: Checksum verification failed!")
            return False
    
    return success


def download_recommended(vram_mb: int, models_dir: Path) -> bool:
    """Download recommended models based on VRAM."""
    print(f"VRAM detected: {vram_mb} MB")
    
    # Always download turbo for drafts
    success = True
    
    if vram_mb >= 12000:
        print("High VRAM detected. Downloading Full + Turbo models...")
        success = download_model("turbo", models_dir) and success
        success = download_model("full", models_dir) and success
    elif vram_mb >= 8000:
        print("Medium VRAM detected. Downloading Turbo model...")
        success = download_model("turbo", models_dir) and success
    else:
        print("Low VRAM detected. Downloading GGUF model...")
        success = download_model("gguf", models_dir) and success
    
    return success


def main():
    import argparse
    
    parser = argparse.ArgumentParser(description="Download Z-Image models")
    parser.add_argument("--variant", choices=["turbo", "full", "gguf", "all", "auto"],
                        default="auto", help="Model variant to download")
    parser.add_argument("--models-dir", type=str, default=None,
                        help="Directory to store models")
    parser.add_argument("--force", action="store_true",
                        help="Force re-download even if exists")
    parser.add_argument("--vram", type=int, default=None,
                        help="Override VRAM detection (MB)")
    
    args = parser.parse_args()
    
    models_dir = Path(args.models_dir) if args.models_dir else get_models_dir()
    
    ok = True
    if args.variant == "all":
        for variant in ["turbo", "full", "gguf"]:
            ok = download_model(variant, models_dir, args.force) and ok
    elif args.variant == "auto":
        # Detect VRAM
        vram_mb = args.vram
        if vram_mb is None:
            try:
                from detect_gpu import get_gpu_info
                info = get_gpu_info()
                vram_mb = info["vram_mb"]
            except ImportError:
                vram_mb = 0
        
        ok = download_recommended(vram_mb, models_dir)
    else:
        ok = download_model(args.variant, models_dir, args.force)

    if not ok:
        raise SystemExit(2)


if __name__ == "__main__":
    main()
